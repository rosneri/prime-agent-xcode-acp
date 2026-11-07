#!/usr/bin/env python3
"""Tests for the prime-agent-xcode-acp bridge.

Run:  python3 tests/test_acp_bridge.py

The unit check (tool-title rewrite) is hermetic. The integration check talks
to a live local prime-agent, so it needs prime-agent installed and configured
(the same one Xcode uses).
"""
import json
import os
import subprocess
import sys
import threading
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIDGE = os.path.join(REPO_ROOT, "prime-agent-xcode-acp")
PRIME_AGENT = os.environ.get(
    "PRIME_AGENT_BIN",
    os.path.expanduser("~/.local/share/prime-agent/prime-agent"),
)

failures = []


def check(name, condition, detail=""):
    status = "ok" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def load_bridge():
    # The bridge is a .py-less executable; SourceFileLoader handles it.
    from importlib.machinery import SourceFileLoader
    return SourceFileLoader("pa_xcode_bridge_under_test", BRIDGE).load_module()


def test_tool_title_rewrite():
    bridge_mod = load_bridge()
    check("python_cell_title returns the full code",
          bridge_mod.python_cell_title("import os\nprint('x')") == "import os\nprint('x')")
    check("python_cell_title caps very long cells",
          bridge_mod.python_cell_title("#" * 3000).endswith("…") and
          len(bridge_mod.python_cell_title("#" * 3000)) <= 2001)
    check("python_cell_title fallback",
          bridge_mod.python_cell_title("   \n\n") == "Run Python code")


def integration():
    if not os.path.exists(PRIME_AGENT):
        print("[skip] integration: prime-agent not found at", PRIME_AGENT)
        return
    proc = subprocess.Popen([BRIDGE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, bufsize=1)
    lines = []

    def reader(stream, label):
        for line in stream:
            lines.append((label, line.strip()))

    for s, l in [(proc.stdout, "OUT"), (proc.stderr, "ERR")]:
        threading.Thread(target=reader, args=(s, l), daemon=True).start()

    def send(msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    time.sleep(1.0)
    send({"jsonrpc": "2.0", "id": "INIT-1", "method": "initialize",
          "params": {"protocolVersion": "1.0.0", "clientCapabilities": {},
                     "clientInfo": {"name": "test", "version": "0"}}})
    time.sleep(2.0)

    init_ok = False
    for _, line in lines:
        if '"INIT-1"' in line and "authMethods" in line:
            try:
                obj = json.loads(line)
                init_ok = obj["result"]["authMethods"] == []
            except Exception:
                pass
    check("initialize accepts string protocolVersion and injects authMethods", init_ok)

    send({"jsonrpc": "2.0", "id": 2, "method": "session/new",
          "params": {"cwd": os.getcwd(), "mcpServers": []}})
    time.sleep(2.0)
    sid = None
    for _, line in lines:
        if '"sessionId"' in line:
            try:
                sid = json.loads(line)["result"]["sessionId"]
            except Exception:
                pass
    check("session/new returns a session id", bool(sid))

    if sid:
        send({"jsonrpc": "2.0", "id": 3, "method": "session/prompt",
              "params": {"sessionId": sid,
                         "prompt": [{"type": "text", "text": "Reply with exactly: done"}]}})
        def turn_finished():
            for _, line in lines:
                try:
                    obj = json.loads(line)
                    if obj.get("id") == 3 and isinstance(obj.get("result"), dict) \
                            and obj["result"].get("stopReason") == "end_turn":
                        return True
                except Exception:
                    continue
            return False

        deadline = time.time() + 180  # model + daemon can be slow under load
        while time.time() < deadline and not turn_finished():
            time.sleep(1)
        check("session/prompt streams a turn to end_turn", turn_finished())
        titles = []
        for _, line in lines:
            try:
                obj = json.loads(line)
                u = obj.get("params", {}).get("update", {})
                if obj.get("method") == "session/update" and u.get("sessionUpdate") == "tool_call":
                    titles.append(u.get("title"))
            except Exception:
                pass
        check("tool-call cards are labeled with code, not 'Python cell'",
              all(t and t != "Python cell" for t in titles), detail=repr(titles))

    proc.stdin.close()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
        proc.wait()


if __name__ == "__main__":
    test_tool_title_rewrite()
    integration()
    if failures:
        print("\nFAILED:", ", ".join(failures))
        sys.exit(1)
    print("\nAll checks passed.")
