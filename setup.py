#!/usr/bin/env python3
"""
AgentRouter Proxy - Universal Cross-Platform Setup & Configuration Wizard
Supports Windows, macOS, and Linux.

Features:
  - Interactive configuration wizard
  - Automatic Tailscale IP detection
  - Choice of Local Loopback (127.0.0.1) or Tailscale Mesh access
  - Choice of On-Demand manual run or Auto-Start on boot (Windows/Linux/macOS)
  - Clear copy-paste details for OpenCode, Cursor, Claude Code, Cline, Roo, Kilo
  - Optional immediate proxy start
"""

import os
import sys
import platform
import subprocess
import shutil
import secrets
import json

# Enable ANSI escape sequences on Windows
if platform.system() == "Windows":
    os.system("")

# Styling
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BOLD = "\033[1m"
C_GRAY = "\033[90m"
C_RESET = "\033[0m"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(SCRIPT_DIR, ".env")


def print_banner():
    print(f"{C_CYAN}{C_BOLD}")
    print("=" * 76)
    print("        AgentRouter Proxy  --  Universal Setup & Configuration        ")
    print(f"        OS: {platform.system()} ({platform.release()})  |  Python: {platform.python_version()}        ")
    print("=" * 76 + f"{C_RESET}\n")


def load_env() -> dict:
    env_vars = {}
    if os.path.isfile(ENV_PATH):
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip().strip("'\"")
        except Exception:
            pass
    return env_vars


def save_env(vars_to_save: dict):
    existing_lines = []
    keys_written = set()
    if os.path.isfile(ENV_PATH):
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                existing_lines = f.readlines()
        except Exception:
            existing_lines = []

    new_lines = []
    for line in existing_lines:
        trimmed = line.strip()
        if trimmed and not trimmed.startswith("#") and "=" in trimmed:
            k = trimmed.split("=", 1)[0].strip()
            if k in vars_to_save:
                new_lines.append(f"{k}={vars_to_save[k]}\n")
                keys_written.add(k)
                continue
        new_lines.append(line)

    for k, v in vars_to_save.items():
        if k not in keys_written:
            new_lines.append(f"{k}={v}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def detect_tailscale_ip() -> str | None:
    """Detect Tailscale IPv4 address via CLI."""
    ts_bin = shutil.which("tailscale")
    if not ts_bin:
        # Common Windows path check
        win_path = r"C:\Program Files\Tailscale\tailscale.exe"
        if os.path.isfile(win_path):
            ts_bin = win_path

    if ts_bin:
        try:
            proc = subprocess.run([ts_bin, "ip", "-4"], capture_output=True, text=True, timeout=3)
            out = proc.stdout.strip()
            if proc.returncode == 0 and out.startswith("100."):
                return out.splitlines()[0].strip()
        except Exception:
            pass
    return None


def mask_key(k: str) -> str:
    if not k or len(k) <= 8:
        return "********"
    return k[:6] + "..." + k[-4:]


def configure_autostart_windows(enable: bool):
    startup_dir = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
    vbs_path = os.path.join(startup_dir, "AgentRouter-Proxy.vbs")
    old_local_vbs = os.path.join(startup_dir, "AgentRouter-Proxy-Local.vbs")
    old_cmd = os.path.join(startup_dir, "AgentRouterLocalProxy.cmd")

    # Clean legacy/old files
    for p in (old_local_vbs, old_cmd):
        if os.path.isfile(p):
            try:
                os.remove(p)
            except Exception:
                pass

    if enable:
        vbs_content = (
            'Option Explicit\n'
            'Dim WshShell\n'
            'Set WshShell = CreateObject("WScript.Shell")\n'
            f'WshShell.Run "wscript.exe ""{os.path.join(SCRIPT_DIR, "run-silent.vbs")}""", 0, False\n'
        )
        try:
            with open(vbs_path, "w", encoding="utf-8") as f:
                f.write(vbs_content)
            print(f" {C_GREEN}[OK]{C_RESET} Installed Windows startup launcher in:\n      {vbs_path}")
        except Exception as e:
            print(f" {C_YELLOW}[WARN]{C_RESET} Could not write to Startup folder: {e}")
    else:
        if os.path.isfile(vbs_path):
            try:
                os.remove(vbs_path)
                print(f" {C_GREEN}[OK]{C_RESET} Removed startup launcher from Windows Startup folder.")
            except Exception as e:
                print(f" {C_YELLOW}[WARN]{C_RESET} Failed to remove startup launcher: {e}")
        else:
            print(f" {C_GREEN}[OK]{C_RESET} Auto-start on boot is disabled.")


def configure_autostart_linux(enable: bool):
    unit_dir = os.path.expanduser("~/.config/systemd/user")
    service_path = os.path.join(unit_dir, "agentrouter-proxy.service")
    py_bin = sys.executable or "/usr/bin/python3"

    if enable:
        os.makedirs(unit_dir, exist_ok=True)
        content = f"""[Unit]
Description=AgentRouter Proxy Service
After=network.target

[Service]
Type=simple
WorkingDirectory={SCRIPT_DIR}
ExecStart={py_bin} {os.path.join(SCRIPT_DIR, 'agentrouter-proxy.py')} 4182
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
"""
        try:
            with open(service_path, "w", encoding="utf-8") as f:
                f.write(content)
            subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
            subprocess.run(["systemctl", "--user", "enable", "--now", "agentrouter-proxy"], capture_output=True)
            print(f" {C_GREEN}[OK]{C_RESET} Created and enabled systemd user service:\n      {service_path}")
        except Exception as e:
            print(f" {C_YELLOW}[WARN]{C_RESET} Could not configure systemd service: {e}")
    else:
        if os.path.isfile(service_path):
            try:
                subprocess.run(["systemctl", "--user", "disable", "--now", "agentrouter-proxy"], capture_output=True)
                os.remove(service_path)
                subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
                print(f" {C_GREEN}[OK]{C_RESET} Disabled and removed systemd user service.")
            except Exception as e:
                print(f" {C_YELLOW}[WARN]{C_RESET} Could not remove systemd service: {e}")


def configure_autostart_macos(enable: bool):
    plist_dir = os.path.expanduser("~/Library/LaunchAgents")
    plist_path = os.path.join(plist_dir, "com.agentrouter.proxy.plist")
    py_bin = sys.executable or "/usr/bin/python3"

    if enable:
        os.makedirs(plist_dir, exist_ok=True)
        content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agentrouter.proxy</string>
    <key>ProgramArguments</key>
    <array>
        <string>{py_bin}</string>
        <string>{os.path.join(SCRIPT_DIR, 'agentrouter-proxy.py')}</string>
        <string>4182</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{SCRIPT_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
"""
        try:
            with open(plist_path, "w", encoding="utf-8") as f:
                f.write(content)
            subprocess.run(["launchctl", "load", "-w", plist_path], capture_output=True)
            print(f" {C_GREEN}[OK]{C_RESET} Installed macOS LaunchAgent:\n      {plist_path}")
        except Exception as e:
            print(f" {C_YELLOW}[WARN]{C_RESET} Could not install LaunchAgent: {e}")
    else:
        if os.path.isfile(plist_path):
            try:
                subprocess.run(["launchctl", "unload", "-w", plist_path], capture_output=True)
                os.remove(plist_path)
                print(f" {C_GREEN}[OK]{C_RESET} Removed macOS LaunchAgent.")
            except Exception as e:
                print(f" {C_YELLOW}[WARN]{C_RESET} Could not remove LaunchAgent: {e}")


def create_desktop_shortcut():
    if platform.system() == "Windows":
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            desk = shell.SpecialFolders("Desktop")
            s = shell.CreateShortcut(os.path.join(desk, "AgentRouter Proxy.lnk"))
            s.TargetPath = os.path.join(SCRIPT_DIR, "run-local.bat")
            s.WorkingDirectory = SCRIPT_DIR
            s.Save()
            # Also sync to OneDrive Desktop if distinct
            alt_desk = os.path.expanduser(r"~\Desktop")
            if os.path.isdir(alt_desk) and alt_desk.lower() != desk.lower():
                s2 = shell.CreateShortcut(os.path.join(alt_desk, "AgentRouter Proxy.lnk"))
                s2.TargetPath = os.path.join(SCRIPT_DIR, "run-local.bat")
                s2.WorkingDirectory = SCRIPT_DIR
                s2.Save()
            print(f" {C_GREEN}[OK]{C_RESET} Desktop shortcut created ('AgentRouter Proxy').")
        except Exception:
            pass


def main():
    print_banner()
    env = load_env()

    # 1. API Key Setup
    current_key = env.get("PROXY_UPSTREAM_API_KEY") or env.get("AGENTROUTER_API_KEY") or ""
    print(f"{C_BOLD}[1/4] Upstream Provider API Key{C_RESET}")
    if current_key:
        print(f" Current key in .env: {C_GREEN}{mask_key(current_key)}{C_RESET}")
        choice = input(f" Keep this key? ({C_BOLD}Y{C_RESET}/n) or paste a new key: ").strip()
        if choice.lower() == "n":
            api_key = input(" Enter your new AgentRouter key (sk-...): ").strip()
        elif choice and not choice.lower().startswith("y"):
            api_key = choice
        else:
            api_key = current_key
    else:
        while True:
            api_key = input(f" Enter your AgentRouter API key ({C_YELLOW}sk-...{C_RESET}): ").strip()
            if api_key:
                break
            print(f" {C_RED}[!] API key cannot be empty.{C_RESET}")
    print()

    # 2. Network Mode Selection
    print(f"{C_BOLD}[2/4] Network & Access Mode{C_RESET}")
    detected_ts = detect_tailscale_ip()
    if detected_ts:
        print(f" {C_GREEN}[OK]{C_RESET} Tailscale connection detected: {C_CYAN}{detected_ts}{C_RESET}")
    else:
        print(f" {C_GRAY}[i] Tailscale was not detected or is offline.{C_RESET}")

    arg_mode = None
    if "--local" in sys.argv:
        arg_mode = "1"
    elif "--tailscale" in sys.argv:
        arg_mode = "2"

    print(" Select how you want to access the proxy:")
    print(f"   {C_BOLD}[1]{C_RESET} Local PC Only (127.0.0.1)  -  [Recommended for local development]")
    print(f"   {C_BOLD}[2]{C_RESET} Tailscale / Mesh Network   -  [Share securely across your devices]")

    default_mode = arg_mode or ("2" if detected_ts else "1")
    mode_input = input(f" Enter option [1/2] (Default: {default_mode}): ").strip() or default_mode

    listen_host = "127.0.0.1"
    auth_token = ""

    if mode_input == "2":
        if detected_ts:
            ts_choice = input(f" Use detected Tailscale IP ({C_CYAN}{detected_ts}{C_RESET})? ({C_BOLD}Y{C_RESET}/n): ").strip().lower()
            if ts_choice != "n":
                listen_host = detected_ts
            else:
                listen_host = input(" Enter custom network IP (e.g. 100.x.y.z): ").strip() or "0.0.0.0"
        else:
            listen_host = input(" Enter your network/Tailscale IP: ").strip() or "0.0.0.0"

        # Client token generation
        existing_token = env.get("PROXY_AUTH_TOKEN", "")
        if existing_token:
            tok_prompt = input(f" Use existing client token ({mask_key(existing_token)})? ({C_BOLD}Y{C_RESET}/n): ").strip().lower()
            if tok_prompt != "n":
                auth_token = existing_token

        if not auth_token:
            auth_token = secrets.token_hex(24)
            print(f" {C_GREEN}[OK]{C_RESET} Generated client auth token: {C_YELLOW}{auth_token}{C_RESET}")
    else:
        listen_host = "127.0.0.1"
        auth_token = ""
    print()

    # 3. Port & Upstream defaults
    port = env.get("PROXY_PORT", "4182")
    upstream = env.get("PROXY_UPSTREAM", "https://agentrouter.org")

    # 4. Auto-Start Configuration
    print(f"{C_BOLD}[3/4] Startup Behavior{C_RESET}")
    print(" Choose how you want to run the proxy:")
    print(f"   {C_BOLD}[1]{C_RESET} On-Demand  -  Click to run when needed (stops when closed)")
    print(f"   {C_BOLD}[2]{C_RESET} Auto-Start -  Runs silently in background on boot")

    autostart_choice = input(" Enter option [1/2] (Default: 1): ").strip() or "1"
    enable_autostart = (autostart_choice == "2")

    sys_os = platform.system()
    if sys_os == "Windows":
        configure_autostart_windows(enable_autostart)
        create_desktop_shortcut()
    elif sys_os == "Linux":
        configure_autostart_linux(enable_autostart)
    elif sys_os == "Darwin":
        configure_autostart_macos(enable_autostart)
    print()

    # 5. Save Configuration to .env
    print(f"{C_BOLD}[4/4] Saving Configuration...{C_RESET}")
    save_data = {
        "PROXY_UPSTREAM": upstream,
        "PROXY_UPSTREAM_API_KEY": api_key,
        "AGENTROUTER_API_KEY": api_key,
        "PROXY_LISTEN_HOST": listen_host,
        "PROXY_PORT": port,
        "PROXY_AUTH_TOKEN": auth_token,
    }
    save_env(save_data)
    print(f" {C_GREEN}[OK]{C_RESET} Configuration successfully written to:\n      {ENV_PATH}\n")

    # 6. Print Tool Configuration Summary Box
    base_url = f"http://{listen_host}:{port}/v1"
    display_token = auth_token if auth_token else "sk-local (or any text - loopback requires no auth)"

    print(f"{C_CYAN}{C_BOLD}" + "=" * 76)
    print("           READY! COPY-PASTE SETTINGS FOR YOUR AI CODING TOOLS            ")
    print("=" * 76 + f"{C_RESET}")
    print(f" OpenCode, Cursor, Claude Code, Cline, Roo Code, Kilo Code, SDKs:")
    print()
    print(f"   {C_BOLD}Base URL:{C_RESET}     {C_GREEN}{base_url}{C_RESET}")
    print(f"   {C_BOLD}API Key:{C_RESET}      {C_YELLOW}{display_token}{C_RESET}")
    print(f"   {C_BOLD}Format:{C_RESET}       OpenAI & Anthropic dual-compatible (auto-detected)")
    print()
    print(f" Health & Usage Endpoints:")
    print(f"   {C_BOLD}Health Check:{C_RESET} http://{listen_host}:{port}/healthz")
    print(f"   {C_BOLD}Models List:{C_RESET}  http://{listen_host}:{port}/v1/models")
    print(f"   {C_BOLD}Live Usage:{C_RESET}   http://{listen_host}:{port}/_usage")
    print()
    print(f" Multi-Project Capability:")
    print(f"   {C_GREEN}* You can use this single proxy in UNLIMITED simultaneous projects & editors!{C_RESET}")
    print(f"   * Just set the Base URL in each project's settings.")
    print(f"{C_CYAN}{C_BOLD}" + "=" * 76 + f"{C_RESET}\n")

    # 7. Start Now Prompt
    start_now = input(f" Start the proxy right now? ({C_BOLD}Y{C_RESET}/n): ").strip().lower()
    if start_now != "n":
        print(f"\n{C_CYAN}[*] Starting AgentRouter Proxy on {listen_host}:{port}...{C_RESET}\n")
        # Ensure clean port on Windows before running
        if platform.system() == "Windows":
            try:
                subprocess.run(
                    f'for /f "tokens=5" %a in (\'netstat -aon 2^>nul ^| findstr ":{port}" ^| findstr "LISTENING"\') do taskkill /f /pid %a >nul 2>&1',
                    shell=True,
                )
            except Exception:
                pass

        cmd = [sys.executable, os.path.join(SCRIPT_DIR, "agentrouter-proxy.py"), str(port)]
        try:
            subprocess.run(cmd)
        except KeyboardInterrupt:
            print(f"\n{C_YELLOW}[INFO] Proxy stopped by user.{C_RESET}")


if __name__ == "__main__":
    main()
