# SSL Pinning Hash Generator — Agentic POC

## Purpose

This POC demonstrates a **tool-calling agent** pattern where an LLM is given a custom tool and autonomously decides when to invoke it to fulfil a user request.

The specific use case is **SSL certificate pinning**: given a URL, a PEM file path, or a raw PEM string, the agent calls the `generate_ssl_pin` tool to compute the SHA-256 SPKI hash required for Android/iOS SSL pinning configuration.

The agent is model-agnostic — it runs against **remote LLMs** (Claude, GPT-4o, Gemini) or **local LLMs via Ollama** (e.g. `qwen3:8b`) using the same code, routed automatically based on the model name.

---

## Architecture

```
agent.py                        ← orchestrator: drives the tool-calling loop
tools/
  ssl_pinning_hash_generator.py ← tool: fetches cert and computes SHA-256 SPKI hash
  schema.py                     ← OpenAI-compatible tool schema definition
```

### How it works

1. User passes a natural language prompt and a model name via CLI.
2. The agent sends the prompt to the LLM along with the tool schema.
3. The LLM decides to call `generate_ssl_pin` with the appropriate `cert_input`.
4. The agent executes the tool, appends the result to the conversation, and calls the LLM again.
5. For **remote models** (Claude, GPT-4o): the LLM exits the loop naturally and returns a final text response.
6. For **Ollama models**: a second call without tools is made to force a final text response (local models tend to loop otherwise).

---

## Technology Stack

| Component | Technology |
|---|---|
| Agent orchestration | Python (custom loop) |
| LLM routing | [LiteLLM](https://github.com/BerriAI/litellm) |
| Remote LLMs | Anthropic Claude, OpenAI GPT-4o, Google Gemini |
| Local LLMs | [Ollama](https://ollama.com) |
| SSL cert fetch | Python `ssl` + `socket` stdlib |
| SPKI hash computation | `openssl` CLI (via `subprocess`) |
| Python version | 3.9+ |

---

## Project Structure

```
work-agents/
├── agent.py                              # Entry point and agent loop
├── tools/
│   ├── __init__.py
│   ├── ssl_pinning_hash_generator.py     # Tool implementation
│   └── schema.py                         # Tool schema for LLM
├── .venv/                                # Virtual environment (not committed)
└── README.md
```

---

## Environment Setup

### 1. Create and activate the virtual environment

```bash
cd /Users/rupesh.chavan/Workspace/AI/work-agents
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install litellm
```

### 3. Set API keys (for remote models)

```bash
export ANTHROPIC_API_KEY="your-key-here"   # For Claude
export OPENAI_API_KEY="your-key-here"      # For GPT-4o
export GEMINI_API_KEY="your-key-here"      # For Gemini
```

### 4. Install and run Ollama (for local models)

Download from [ollama.com](https://ollama.com), then:

```bash
ollama pull qwen3:8b       # Pull the model
ollama serve               # Start the Ollama server (if not already running)
```

Verify the model is loaded:

```bash
ollama ps
```

---

## Running the Agent

```bash
python3 agent.py "<model>" "<prompt>"
```

### Examples

**With Claude (remote):**
```bash
python3 agent.py "claude-sonnet-4-6" "Generate SSL pin for https://google.com"
```

**With GPT-4o (remote):**
```bash
python3 agent.py "gpt-4o" "Generate SSL pin for https://apple.com"
```

**With local Ollama model:**
```bash
python3 agent.py "qwen3:8b" "Generate SSL pin for https://google.com"
```

**With a PEM file:**
```bash
python3 agent.py "claude-sonnet-4-6" "Generate SSL pin for /path/to/cert.pem"
```

### Expected output

```
Model: claude-sonnet-4-6
Input: Generate SSL pin for https://google.com

[Agent] Calling tool: generate_ssl_pin with args: {'cert_input': 'https://google.com'}

SHA-256 SPKI Hash: 8DKJU//UFcNjiEPhNqsXQ1ceewuqgq7Rc1l+j99p9PE=
```

The agent also returns ready-to-use Android (`network_security_config.xml`) and iOS (`Info.plist`) snippets when run with Claude.

---

## Tool: `generate_ssl_pin`

Accepts any of:

| Input type | Example |
|---|---|
| HTTPS URL | `https://google.com` |
| PEM file path | `/path/to/cert.pem` |
| Raw PEM string | `-----BEGIN CERTIFICATE-----\n...` |

Returns:
```json
{ "sha256_hash": "8DKJU//UFcNjiEPhNqsXQ1ceewuqgq7Rc1l+j99p9PE=" }
```

The hash is computed using the standard openssl pipeline:
```bash
openssl x509 -pubkey -noout | openssl pkey -pubin -outform der | openssl dgst -sha256 -binary | openssl enc -base64
```

---

## Model Routing Logic

LiteLLM is used as a unified completion layer. The agent auto-detects the provider:

| Model prefix | Routed to |
|---|---|
| `claude-` | Anthropic API |
| `gpt-` | OpenAI API |
| `gemini/` | Google Gemini API |
| anything else | Ollama at `http://localhost:11434` |

You do **not** need to prefix local model names with `ollama/` — the agent adds it automatically.

---

## Known Limitations

- **Local models and tool loops**: Ollama models (including `qwen3:8b`) tend to call tools repeatedly instead of synthesising a final answer. This is worked around by making a second LLM call without tools after the first tool result is received.
- **Certificate rotation**: SSL pins are tied to the live certificate at the time of generation. Domains like Google rotate certs frequently — regenerate the pin periodically and always include a backup pin.
- **openssl required**: The tool shells out to `openssl`. Ensure it is available on your `PATH` (`which openssl`).
