# Provider-Neutral Proxy Design

## Goal

Provide a reusable local proxy for coding tools that can route OpenAI-compatible and Anthropic requests through a configurable upstream provider. The repository is public, so credentials and user prompts must never be embedded in source, examples, or routine logs.

## Architecture

- Keep the existing Python standard-library implementation so the proxy runs on Windows and Linux without third-party dependencies.
- Use one combined entry point for automatic OpenAI/Anthropic request detection.
- Read the upstream URL, upstream key, protocol mode, listen address, incoming access token, and limits from environment variables.
- Preserve the existing SSE cleanup and Anthropic-to-OpenAI conversion behavior, while making the educational preamble opt-in rather than automatic.
- Keep the specialized scripts as compatibility entry points during migration.

## Security Defaults

- Bind to `127.0.0.1` by default.
- Require `PROXY_AUTH_TOKEN` when listening on a non-loopback address, including a Tailscale address.
- Use a separate incoming proxy token from the upstream provider key.
- Never write request bodies, API keys, or full prompts to disk. Debug output is metadata-only.
- Protect health and statistics endpoints with the same incoming token when network access is enabled.
- Restrict body size and use bounded upstream timeouts.
- Do not forward the client Authorization header to the upstream; inject only the configured upstream credential.

## Wyse Deployment

- Copy the repository to the Wyse PC through the existing `wyse` SSH alias.
- Store secrets in a local `.env` file excluded by git, or in the Windows service/task environment.
- Bind to the Wyse Tailscale IP only when remote access is needed.
- Verify with a local mock upstream and a no-secret smoke test before any real provider request.

## Documentation

The README will document setup on Windows, Linux, OpenCode, generic OpenAI-compatible clients, Anthropic clients, Tailscale access, environment variables, troubleshooting, and the referral link supplied by the owner:

https://agentrouter.org/register?aff=M69e

## Validation

- Syntax-compile all Python entry points.
- Run unit tests for authentication, request normalization, null cleanup, and SSE filtering.
- Run a mock-upstream streaming smoke test.
- On Wyse, repeat the syntax and mock smoke tests and verify the listener is reachable only at the configured address.
- A real provider smoke test requires a newly issued key; exposed keys are not used.
