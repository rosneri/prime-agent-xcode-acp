# prime-agent-xcode-acp

Run [prime-agent](https://github.com/primeintellect-ai/prime-agent) as a coding agent inside **Xcode 26 / 27** over the [Agent Client Protocol](https://agentclientprotocol.com/).

Xcode 27 speaks ACP v2: it sends `protocolVersion` as a *string* and requires `authMethods` on the handshake result. prime-agent's ACP mode (`--mode acp`) speaks v1 and expects an *integer* version. Left alone, Xcode reports `JSON-RPC request with ID ... failed to produce a response` or `The data couldn't be read because it is missing.` This bridge makes the two agree, so **Prime Agent** shows up in Xcode's agent picker and streams replies like Claude does — including Xcode's injected `xcode-tools` MCP server.

## Features

- **One executable, no build step** — plain Python 3 using only the standard library (system `/usr/bin/python3`).
- **Fixes the ACP handshake** Xcode 27 requires:
  - `protocolVersion: "1.0.0"` (string) → integer on the way in.
  - `authMethods: []` injected into the `initialize` result (Xcode 27's decoder demands the key).
- **Relays everything else verbatim** — sessions, prompts, streaming updates, MCP traffic.
- **Readable tool cards** — Python REPL tool calls show the full code of the cell instead of the generic `Python cell`.
- **Quiet mode** — optionally drop the model's reasoning stream from the chat.
- **Traffic log** — every ACP message is written to a file for debugging, no guessing.

## How it works

```
Xcode 27 (ACP v2 client)
        │  stdio JSON-RPC (protocolVersion "1.0.0")
        ▼
prime-agent-xcode-acp  (this bridge)
        │  stdio JSON-RPC (protocolVersion 1, authMethods added)
        ▼
prime-agent --mode acp
```

The bridge is an stdio relay with two small rewrites on the wire: it normalizes the
inbound `protocolVersion`, and it adds the `authMethods` field to the outbound
`initialize` result. Everything else passes through byte-for-byte.

## Requirements

- macOS with **Xcode 26 or 27** (agent UI: `Settings → Intelligence → Agents`).
- **Python 3** at `/usr/bin/python3` (ships with macOS).
- **prime-agent** installed and configured — the same models, keys, and providers you already use.
  The bridge looks for it at `~/.local/share/prime-agent/prime-agent` by default.

## Installation

```sh
# Install to ~/.local/bin (anywhere on PATH works)
curl -fsSL https://raw.githubusercontent.com/rosneri/prime-agent-xcode-acp/main/prime-agent-xcode-acp \
  -o ~/.local/bin/prime-agent-xcode-acp
chmod +x ~/.local/bin/prime-agent-xcode-acp
```

Or clone the repo and run it from there:

```sh
git clone https://github.com/rosneri/prime-agent-xcode-acp.git
```

## Add the agent to Xcode

1. Open `Settings → Intelligence → Agents`.
2. Click **Add an Agent…** (or edit an existing "Prime Agent" entry).
3. Fill in:
   - **Name:** `Prime Agent`
   - **Executable:** `/Users/<you>/.local/bin/prime-agent-xcode-acp`
   - **Arguments:** *(empty)*
   - **Environment:** *(optional, see below)*
4. Save, then send a message to **Prime Agent**. It should stream a reply.

> **Important:** keep `--mode acp` out of the Executable field — the whole command line
> belongs nowhere but the Executable path. Xcode launches the Executable as one program.

### Environment variables (all optional)

| Variable | Default | Purpose |
| --- | --- | --- |
| `PRIME_AGENT_BIN` | `~/.local/share/prime-agent/prime-agent` | Path to the prime-agent executable. |
| `PRIME_AGENT_XCODE_ACP_HIDE_THOUGHTS` | unset (`1` to enable) | Drop `agent_thought_chunk` updates so Xcode's chat shows only messages and tool calls. |
| `PRIME_AGENT_XCODE_ACP_LOG` | `/tmp/prime-agent-xcode-acp.log` | Where every ACP message (in and out) is appended. |

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `JSON-RPC request with ID ... failed to produce a response` | The Executable field contains the whole command line (`.../prime-agent --mode acp`). Put only the bridge path in Executable, leave Arguments empty. |
| `The data couldn't be read because it is missing.` | Xcode 27 requires `authMethods` on the `initialize` result; the current bridge injects it. Make sure Xcode is launching the bridge (not the raw prime-agent binary). |
| Tool cards say `Python cell` (or show only one line) | Old bridge version. Current versions label each card with the cell's full code. |
| The agent still fails | Read `/tmp/prime-agent-xcode-acp.log` — it shows exactly what Xcode sent and what prime-agent answered. Restart Xcode after changing the agent config. |

## Development

```sh
git clone https://github.com/rosneri/prime-agent-xcode-acp.git
cd prime-agent-xcode-acp

# Unit checks run without prime-agent; the integration check needs a
# configured local prime-agent and talks to it over the bridge.
python3 tests/test_acp_bridge.py
```

## License

[MIT](LICENSE)
