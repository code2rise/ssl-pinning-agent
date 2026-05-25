# SSL Pinning Agent — POC

A tool-calling AI agent that generates SHA-256 SPKI hashes for SSL certificate pinning.
Runs against any LLM — Claude, GPT-4o, Gemini, or a local Ollama model — using the same code.

---

## Table of Contents

1. [What this POC demonstrates](#what-this-poc-demonstrates)
2. [Fundamental Concepts](#fundamental-concepts)
   - [Tool Use / Function Calling](#1-tool-use--function-calling)
   - [The Agentic Loop](#2-the-agentic-loop)
   - [LiteLLM — Model-Agnostic Routing](#3-litellm--model-agnostic-routing)
   - [SSL Pinning & SPKI Hashing](#4-ssl-pinning--spki-hashing)
3. [Architecture](#architecture)
4. [Key Design Decisions](#key-design-decisions)
5. [Project Structure](#project-structure)
6. [Environment Setup](#environment-setup)
7. [Running the Agent](#running-the-agent)
8. [Known Limitations & Learnings](#known-limitations--learnings)

---

## What this POC demonstrates

This project is a **minimal but complete example of an agentic AI system**. The core idea is:

> Instead of the LLM answering directly from its training knowledge, it is given a *tool* it can call to get real, live data — and it decides autonomously when and how to use that tool.

The concrete task is SSL certificate pinning: given a URL, the agent fetches the live certificate, computes a cryptographic hash of its public key, and returns it in a format ready to paste into an Android or iOS app.

The POC deliberately keeps the orchestration code simple (~90 lines) so the agentic pattern is easy to follow without noise.

---

## Fundamental Concepts

### 1. Tool Use / Function Calling

**What it is:**
Tool use (also called function calling) is a capability where an LLM can, instead of generating a plain text answer, output a structured request to call a function. The application receives this request, executes the function, and sends the result back to the LLM, which then incorporates it into its final response.

**Why it matters:**
LLMs have a training knowledge cutoff and cannot access the internet or your systems. Tool use bridges this gap. The LLM contributes reasoning and decision-making; external tools contribute real-time data, computation, or side effects.

**How it works here:**
The `generate_ssl_pin` tool is registered with the LLM via a JSON schema. When the user asks "Generate SSL pin for https://google.com", the LLM does not guess the hash — it calls the tool with `cert_input: "https://google.com"`, receives the actual computed hash, and returns it to the user.

**The tool schema** (`tools/schema.py`) describes the tool to the LLM in a format all major providers understand:
```json
{
  "type": "function",
  "function": {
    "name": "generate_ssl_pin",
    "description": "...",
    "parameters": {
      "type": "object",
      "properties": {
        "cert_input": { "type": "string", "description": "..." }
      },
      "required": ["cert_input"]
    }
  }
}
```
The LLM uses the `description` fields to understand what the tool does and what arguments to pass. **The quality of these descriptions directly affects how reliably the LLM uses the tool.**

---

### 2. The Agentic Loop

**What it is:**
An agentic loop is a repeated cycle where the LLM is called, its output is inspected, and if it requested a tool call, the tool is executed and the result is fed back to the LLM for another round. This continues until the LLM produces a plain text response (no tool call), at which point the loop exits.

**Visualised:**

```
User Input
    │
    ▼
┌─────────────────────────────────────────┐
│              Agentic Loop               │
│                                         │
│  ┌──────────┐    tool_call?    ┌──────┐ │
│  │   LLM    │ ──── YES ──────► │ Tool │ │
│  │  Call    │                  │ Exec │ │
│  └──────────┘ ◄── result ───── └──────┘ │
│       │                                 │
│    no tool_call?                        │
│       │                                 │
└───────┼─────────────────────────────────┘
        ▼
   Final Answer
```

**Why a loop and not a single call?**
A single tool call is enough for simple tasks (like this one). But the loop pattern supports multi-step reasoning — e.g. an agent that first searches for a domain, then fetches its cert, then looks up revocation status. Each step can trigger a different tool. The loop handles all of these uniformly.

**The conversation history** is the memory of the loop. Every message — user input, LLM responses, tool calls, and tool results — is accumulated in a `messages` list and sent in full on every LLM call. This is how the LLM "remembers" what has already happened within a session.

**`MAX_ITERATIONS`** is a safety guard. Without it, a misbehaving model could loop forever. Five iterations is more than enough for a single-tool task.

---

### 3. LiteLLM — Model-Agnostic Routing

**What it is:**
LiteLLM is a Python library that provides a single, unified `completion()` interface that routes to 100+ LLM providers (Anthropic, OpenAI, Google, Ollama, etc.) by translating the request and response formats transparently.

**Why use it here:**
Without LiteLLM, switching from Claude to GPT-4o would require rewriting the API call, authentication, and response parsing — each provider has a different SDK and response structure. LiteLLM eliminates that entirely.

**How the provider is detected:**
The agent inspects the model name prefix to decide routing:

| Model name starts with | Routed to |
|---|---|
| `claude-` | Anthropic API |
| `gpt-` | OpenAI API |
| `gemini/` | Google Gemini API |
| anything else | Ollama (local) at `http://localhost:11434` |

This means you do not need to prefix local model names with `ollama/` — the agent infers it.

---

### 4. SSL Pinning & SPKI Hashing

**What SSL Pinning is:**
SSL pinning is a mobile app security technique where the app is hardcoded to only accept a specific server certificate (or public key). If an attacker intercepts traffic and presents a different certificate — even one signed by a trusted CA — the app rejects it. This defends against man-in-the-middle (MITM) attacks.

**What SPKI is:**
SPKI stands for Subject Public Key Info. Instead of pinning the entire certificate (which changes on every renewal), you pin the *public key* extracted from the certificate. Public keys remain stable across renewals as long as the server doesn't regenerate its key pair. This is the recommended approach.

**How the hash is computed:**
The `generate_ssl_pin` tool runs this OpenSSL pipeline:

```
Certificate (PEM)
       │
       ▼
openssl x509 -pubkey -noout       ← extract the public key
       │
       ▼
openssl pkey -pubin -outform der  ← convert to DER binary format (SPKI structure)
       │
       ▼
openssl dgst -sha256 -binary      ← compute SHA-256 hash of the DER bytes
       │
       ▼
openssl enc -base64               ← base64-encode for embedding in config files
       │
       ▼
  "8DKJU//UFcNji..."              ← the pin
```

**How the cert is fetched from a URL:**
Python's `ssl` + `socket` stdlib is used to establish a TLS connection and extract the raw DER-encoded certificate bytes directly, without making an HTTP request. This is more reliable than using `urllib` because it captures the cert at the TLS handshake level before any HTTP parsing.

---

## Architecture

```
work-agents/
├── agent.py                           ← orchestrator: drives the agentic loop
└── tools/
    ├── ssl_pinning_hash_generator.py  ← tool implementation
    └── schema.py                      ← tool schema (describes the tool to the LLM)
```

**Data flow for `python3 agent.py "claude-sonnet-4-6" "Generate SSL pin for https://google.com"`:**

```
CLI args
  │
  ▼
run_agent()
  │
  ├─► Build messages list (system prompt + user message)
  │
  ├─► Detect provider from model name
  │
  └─► LOOP:
        │
        ├─► litellm.completion(model, messages, tools, tool_choice="auto")
        │         └─► LLM decides: call generate_ssl_pin(cert_input="https://google.com")
        │
        ├─► Append LLM response to messages
        │
        ├─► Execute generate_ssl_pin("https://google.com"):
        │       ├─► Open TLS socket to google.com:443
        │       ├─► Extract DER certificate bytes
        │       ├─► Convert to PEM, write to temp file
        │       ├─► Run openssl pipeline → SHA-256 base64 hash
        │       └─► Return {"sha256_hash": "8DKJU//..."}
        │
        ├─► Append tool result to messages
        │
        └─► [Ollama only] Force final text call without tools
              └─► LLM synthesises answer from tool result → return to user
```

---

## Key Design Decisions

### Decision 1: LiteLLM over provider-specific SDKs
**Rationale:** The primary goal of this POC was to demonstrate a model-agnostic agent. LiteLLM's unified interface made it possible to test the same agent against Claude (remote) and qwen3:8b (local) without any code changes to the core loop.

### Decision 2: Tool schema in a separate `schema.py`
**Rationale:** The schema is the contract between the agent and the LLM. Keeping it separate from the tool implementation makes it easy to update descriptions (which affect LLM behaviour) without touching business logic, and vice versa.

### Decision 3: SSLContext.wrap_socket() instead of ssl.wrap_socket()
**Rationale:** `ssl.wrap_socket()` is deprecated in Python 3.x and does not support `server_hostname`, which is required for SNI (Server Name Indication) — a standard part of TLS for servers hosting multiple domains. `SSLContext.wrap_socket()` is the correct modern API.

### Decision 4: OpenSSL CLI via subprocess for hash computation
**Rationale:** The `openssl` CLI is available on every macOS and Linux machine by default. Using it via `subprocess` avoids adding a cryptography library dependency (like `pyOpenSSL` or `cryptography`) to the project. For a POC, this is a pragmatic trade-off.

### Decision 5: Ollama-specific two-call pattern
**Rationale:** Local models (tested with `qwen2.5-coder:7b` and `qwen3:8b`) consistently re-invoked the tool after receiving its result instead of generating a final answer. Remote models (Claude) handle this correctly. The fix is to make a second LLM call after tool execution *without* the tools parameter, forcing the model to produce a text response. This workaround is scoped to `ollama/` models only to avoid affecting Claude's behaviour.

### Decision 6: `/no_think` in the system prompt
**Rationale:** Qwen3 models have a built-in "thinking" mode that emits internal reasoning tokens before the response. This interferes with tool-call parsing in LiteLLM. Prefixing the system prompt with `/no_think` disables this mode, making the model's output predictable and parseable.

### Decision 7: Provider detection by model name prefix
**Rationale:** Rather than requiring the user to always type `ollama/qwen3:8b`, the agent infers the provider from the model name. Known remote prefixes (`claude-`, `gpt-`, `gemini/`) are checked first; everything else is treated as a local Ollama model. This keeps the CLI ergonomic.

---

## Project Structure

```
work-agents/
├── agent.py                           # Entry point and agentic loop
├── tools/
│   ├── __init__.py
│   ├── ssl_pinning_hash_generator.py  # Tool: fetches cert, computes hash
│   └── schema.py                      # Tool schema definition for LLM
├── .claude/
│   └── settings.json                  # Claude Code project settings (env vars)
├── .gitignore
└── README.md
```

---

## Environment Setup

### Prerequisites
- Python 3.9+
- `openssl` on your PATH (`which openssl` to verify)
- Ollama installed (for local model usage): [ollama.com](https://ollama.com)

### 1. Create and activate the virtual environment

```bash
cd /path/to/work-agents
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install litellm
```

### 3. API keys for remote models

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # Claude
export OPENAI_API_KEY="sk-..."          # GPT-4o
export GEMINI_API_KEY="..."             # Gemini
```

> These are also configurable in `.claude/settings.json` under the `"env"` key for persistence across Claude Code sessions.

### 4. Local model setup (Ollama)

```bash
ollama pull qwen3:8b     # download the model (~5GB)
ollama serve             # start the server (if not already running)
ollama ps                # verify the model is loaded
```

---

## Running the Agent

```bash
# Activate venv first
source .venv/bin/activate

# Syntax
python3 agent.py "<model>" "<prompt>"
```

### Examples

```bash
# Remote — Claude
python3 agent.py "claude-sonnet-4-6" "Generate SSL pin for https://google.com"

# Remote — GPT-4o
python3 agent.py "gpt-4o" "Generate SSL pin for https://apple.com"

# Local — Ollama
python3 agent.py "qwen3:8b" "Generate SSL pin for https://github.com"

# From a PEM file
python3 agent.py "claude-sonnet-4-6" "Generate SSL pin for /path/to/cert.pem"

# From a raw PEM string (wrap in quotes)
python3 agent.py "claude-sonnet-4-6" "Generate SSL pin for -----BEGIN CERTIFICATE-----\n..."
```

### Expected output

```
Model: claude-sonnet-4-6
Input: Generate SSL pin for https://google.com

[Agent] Calling tool: generate_ssl_pin with args: {'cert_input': 'https://google.com'}

SHA-256 SPKI Hash: 8DKJU//UFcNjiEPhNqsXQ1ceewuqgq7Rc1l+j99p9PE=

Android (network_security_config.xml):
  <pin digest="SHA-256">8DKJU//UFcNjiEPhNqsXQ1ceewuqgq7Rc1l+j99p9PE=</pin>
```

---

## Known Limitations & Learnings

| Issue | Root Cause | Workaround Applied |
|---|---|---|
| Local models loop indefinitely on tool results | `qwen3:8b` / `qwen2.5-coder` don't reliably exit the tool-calling loop | Second LLM call without tools forces a text response |
| `ssl.wrap_socket()` TypeError | Deprecated API; doesn't support `server_hostname` | Replaced with `SSLContext.wrap_socket()` |
| `qwen3` thinking tokens break tool parsing | Qwen3's internal reasoning mode emits extra tokens | `/no_think` prefix in system prompt disables it |
| Cert pins expire | Google and other large domains rotate certs frequently | Regenerate pins after renewal; add backup pins |
| `openssl` required on PATH | Hash computation shells out to the CLI | Ensure `openssl` is installed (pre-installed on macOS/Linux) |
