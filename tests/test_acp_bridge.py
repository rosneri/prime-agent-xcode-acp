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
import tempfile
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


def test_skill_autoload():
    bridge_mod = load_bridge()
    skill_file = os.path.join(REPO_ROOT, "skills", "xcode-windows", "SKILL.md")
    with open(skill_file, encoding="utf-8") as f:
        bundled = f.read()

    check("bundled skill is embedded for single-file installs",
          bridge_mod.SKILL_MD.strip() == bundled.strip())
    check("skill frontmatter matches its directory name",
          bundled.startswith("---\nname: xcode-windows\n"))

    saved = {name: os.environ.pop(name, None)
             for name in (bridge_mod.SKILL_PATH_ENV, bridge_mod.NO_SKILL_ENV)}
    try:
        default_cmd = bridge_mod.child_command()
        check("--skill is passed by default",
              default_cmd[-2] == "--skill" and
              default_cmd[-1].endswith(os.path.join("skills", "xcode-windows", "SKILL.md")),
              detail=repr(default_cmd))
        check("default skill path exists", os.path.isfile(default_cmd[-1]),
              detail=default_cmd[-1])

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(bundled)
            override = fh.name
        try:
            os.environ[bridge_mod.SKILL_PATH_ENV] = override
            override_cmd = bridge_mod.child_command()
            check("PRIME_AGENT_XCODE_ACP_SKILL overrides the path",
                  override_cmd[-2:] == ["--skill", override],
                  detail=repr(override_cmd))
        finally:
            os.environ.pop(bridge_mod.SKILL_PATH_ENV, None)
            os.remove(override)

        os.environ[bridge_mod.NO_SKILL_ENV] = "1"
        check("PRIME_AGENT_XCODE_ACP_NO_SKILL removes --skill",
              "--skill" not in bridge_mod.child_command())
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_skill_materialized_for_single_file_install():
    bridge_mod = load_bridge()
    saved_env = {name: os.environ.pop(name, None)
                 for name in (bridge_mod.SKILL_PATH_ENV, bridge_mod.NO_SKILL_ENV)}
    saved_repo, saved_install = bridge_mod.REPO_SKILL, bridge_mod.INSTALL_SKILL
    try:
        with tempfile.TemporaryDirectory() as tmp:
            bridge_mod.REPO_SKILL = os.path.join(tmp, "missing", "SKILL.md")
            bridge_mod.INSTALL_SKILL = os.path.join(
                tmp, "install", "skills", "xcode-windows", "SKILL.md")
            path = bridge_mod.resolve_skill_path()
            written = ""
            if path and os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    written = f.read()
            check("bundled skill is written when no copy is installed",
                  path == bridge_mod.INSTALL_SKILL and
                  written.strip() == bridge_mod.SKILL_MD.strip())
    finally:
        bridge_mod.REPO_SKILL, bridge_mod.INSTALL_SKILL = saved_repo, saved_install
        for name, value in saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


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
    test_skill_autoload()
    test_skill_materialized_for_single_file_install()
    integration()
    if failures:
        print("\nFAILED:", ", ".join(failures))
        sys.exit(1)
    print("\nAll checks passed.")
