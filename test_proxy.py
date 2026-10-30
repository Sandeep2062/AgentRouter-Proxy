import importlib.util
import json
import pathlib
import threading
import urllib.error
import urllib.request
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer


MODULE_PATH = pathlib.Path(__file__).with_name("agentrouter-proxy.py")
spec = importlib.util.spec_from_file_location("provider_proxy", MODULE_PATH)
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


class ProxyBehaviorTests(unittest.TestCase):
    def test_load_env_file(self):
        import tempfile
        import os
        with tempfile.NamedTemporaryFile('w', delete=False, encoding='utf-8') as f:
            f.write('# Comment\nTEST_ENV_KEY_123=test_val_456\n')
            temp_name = f.name
        try:
            proxy.load_env_file(temp_name)
            self.assertEqual(os.environ.get('TEST_ENV_KEY_123'), 'test_val_456')
        finally:
            if 'TEST_ENV_KEY_123' in os.environ:
                del os.environ['TEST_ENV_KEY_123']
            if os.path.exists(temp_name):
                os.remove(temp_name)

    def test_clean_request_removes_null_values(self):
        raw = json.dumps({"model": "demo", "optional": None, "nested": {"keep": 1, "drop": None}}).encode()
        cleaned = json.loads(proxy.clean_request_body(raw))
        self.assertEqual(cleaned, {"model": "demo", "nested": {"keep": 1}})

    def test_responses_model_request_and_response_translation(self):
        payload = {
            "model": "gpt-6.1-sol",
            "messages": [{"role": "user", "content": "hello"}],
        }
        path, body = proxy.normalize_request_body(json.dumps(payload).encode(), "/v1/chat/completions")
        self.assertEqual(path, "/v1/responses")
        req_obj = json.loads(body)
        self.assertEqual(req_obj["model"], "gpt-6.1-sol")
        self.assertEqual(req_obj["input"], [{"role": "user", "content": "hello"}])
        self.assertTrue(req_obj["_converted_from_chat"])

        # Test output translation
        responses_output = {
            "id": "resp_test_123",
            "model": "gpt-6.1-sol",
            "created_at": 1234567,
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "hello back"}]
                }
            ],
            "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}
        }
        chat_comp = proxy.responses_to_chat_completion(responses_output, "gpt-6.1-sol")
        self.assertEqual(chat_comp["object"], "chat.completion")
        self.assertEqual(chat_comp["choices"][0]["message"]["content"], "hello back")
        self.assertEqual(chat_comp["usage"]["total_tokens"], 7)


    def test_responses_multi_turn_tool_calling_conversion(self):
        # OpenCode Turn 2: system + user + assistant tool_call (content null) + tool result
        incoming_messages = [
            {"role": "system", "content": "You are a coding assistant."},
            {"role": "user", "content": "find 3526.md"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_search_9988",
                        "type": "function",
                        "function": {
                            "name": "search",
                            "arguments": '{"path":"3526.md"}'
                        }
                    }
                ]
            },
            {
                "role": "tool",
                "tool_call_id": "call_search_9988",
                "content": "File 3526.md found."
            }
        ]

        converted = proxy.chat_messages_to_responses_input(incoming_messages)
        self.assertEqual(len(converted), 4)

        # 1. System message has content
        self.assertEqual(converted[0]["role"], "system")
        self.assertEqual(converted[0]["content"], "You are a coding assistant.")

        # 2. User message has content
        self.assertEqual(converted[1]["role"], "user")
        self.assertEqual(converted[1]["content"], "find 3526.md")

        # 3. Assistant tool_call is translated to top-level function_call item (not empty message with missing content)
        self.assertEqual(converted[2]["type"], "function_call")
        self.assertEqual(converted[2]["call_id"], "call_search_9988")
        self.assertEqual(converted[2]["name"], "search")
        self.assertEqual(converted[2]["arguments"], '{"path":"3526.md"}')

        # 4. Tool output is translated to top-level function_call_output
        self.assertEqual(converted[3]["type"], "function_call_output")
        self.assertEqual(converted[3]["call_id"], "call_search_9988")
        self.assertEqual(converted[3]["output"], "File 3526.md found.")

        # Test request normalization end-to-end
        payload = {
            "model": "gpt-6.1-sol",
            "messages": incoming_messages,
        }
        path, body = proxy.normalize_request_body(json.dumps(payload).encode(), "/v1/chat/completions")
        self.assertEqual(path, "/v1/responses")
        req_obj = json.loads(body)
        self.assertEqual(req_obj["input"], converted)
        # Every item that has a 'role' MUST have 'content'
        for item in req_obj["input"]:
            if "role" in item:
                self.assertIn("content", item)
                self.assertIsNotNone(item["content"])

    def test_anthropic_payload_is_converted(self):
        payload = {
            "model": "demo-model",
            "max_tokens": 32,
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
        }
        path, body = proxy.normalize_request_body(json.dumps(payload).encode(), "/v1/messages")
        normalized = json.loads(body)
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(normalized["messages"][-1], {"role": "user", "content": "hello"})
        self.assertEqual(normalized["max_completion_tokens"], 32)

    def test_sse_null_and_billing_events_are_filtered(self):
        self.assertIsNone(proxy.clean_sse_line(b"data: null\n\n"))
        billing = b'data: {"object":"billing.summary"}\n\n'
        self.assertIsNone(proxy.clean_sse_line(billing))
        self.assertIsNotNone(proxy.clean_sse_line(b'data: {"choices":[]}\n\n'))

    def test_content_block_detection_is_structured(self):
        blocked = b'{"error":{"type":"content_blocked"}}'
        normal = b'{"choices":[{"message":{"content":"content-blocked is a phrase"}}]}'
        self.assertTrue(proxy.is_content_blocked(blocked))
        self.assertFalse(proxy.is_content_blocked(normal))

    def test_end_to_end_auth_and_upstream_key_isolation(self):
        received = {}

        class MockUpstream(BaseHTTPRequestHandler):
            def do_POST(self):
                received["authorization"] = self.headers.get("Authorization")
                length = int(self.headers.get("Content-Length", 0))
                received["body"] = self.rfile.read(length)
                body = b'{"choices":[{"message":{"content":"ok"}}]}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        upstream = HTTPServer(("127.0.0.1", 0), MockUpstream)
        proxy.UPSTREAM = f"http://127.0.0.1:{upstream.server_port}"
        proxy.API_KEY = "upstream-secret"
        proxy.PROXY_AUTH_TOKEN = "client-secret"
        proxy_server = proxy.ThreadedHTTPServer(("127.0.0.1", 0), proxy.ProxyHandler)
        threads = [
            threading.Thread(target=upstream.serve_forever, daemon=True),
            threading.Thread(target=proxy_server.serve_forever, daemon=True),
        ]
        for thread in threads:
            thread.start()
        try:
            url = f"http://127.0.0.1:{proxy_server.server_port}/v1/chat/completions"
            request = urllib.request.Request(
                url,
                data=b'{"model":"demo","messages":[{"role":"user","content":"hello"}]}',
                headers={"Authorization": "Bearer client-secret", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status, 200)
            self.assertEqual(received["authorization"], "Bearer upstream-secret")

            unauthorized = urllib.request.Request(url, data=b"{}", method="POST")
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(unauthorized)
            self.assertEqual(error.exception.code, 401)
        finally:
            proxy_server.shutdown()
            upstream.shutdown()
            proxy_server.server_close()
            upstream.server_close()


if __name__ == "__main__":
    unittest.main()