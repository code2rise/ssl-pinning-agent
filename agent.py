# agent.py
#
# Orchestrates the agentic loop: sends user input to an LLM, executes any tool
# calls the LLM requests, feeds results back, and repeats until the LLM produces
# a plain text final answer.
#
# Supports remote models (Claude, GPT-4o, Gemini) and local Ollama models
# via a single LiteLLM interface. Provider is inferred from the model name.

import json
import litellm
from tools.ssl_pinning_hash_generator import generate_ssl_pin
from tools.schema import SSL_PIN_TOOL_SCHEMA

# TOOL_REGISTRY maps the tool name (as the LLM knows it from the schema) to the
# actual Python function. When the LLM requests a tool call, we look it up here.
# Adding new tools = add the function + schema, then register it here.
TOOL_REGISTRY = {
    "generate_ssl_pin": generate_ssl_pin
}

def run_agent(user_input: str, model: str) -> str:
    """
    Run the agentic loop for the given user input and model.

    model examples:
      "claude-sonnet-4-6"       → Anthropic API
      "gpt-4o"                  → OpenAI API
      "gemini/gemini-1.5-pro"   → Google Gemini API
      "qwen3:8b"                → Ollama (local), auto-prefixed to "ollama/qwen3:8b"
    """

    # The conversation history is the agent's working memory within a session.
    # Every LLM call receives the full history so the model understands context.
    # System prompt sets the agent's role and, for Ollama models, includes
    # "/no_think" to disable Qwen3's internal reasoning mode which breaks
    # tool-call parsing in LiteLLM.
    messages = [
        {
            "role": "system",
            "content": (
                "/no_think\n"
                "You are an SSL pinning assistant. "
                "When given a certificate (file path, PEM string, or URL), "
                "call the generate_ssl_pin tool ONCE to get the SHA-256 hash. "
                "After receiving the tool result, immediately return the final answer to the user. "
                "Do NOT call the tool again if you already have the result."
            )
        },
        {"role": "user", "content": user_input}
    ]

    MAX_ITERATIONS = 5  # Safety cap — prevents infinite loops on misbehaving models

    # Infer provider from model name so the caller doesn't need to manage prefixes.
    # Known remote providers are checked first; everything else routes to Ollama.
    REMOTE_PREFIXES = ("claude-", "gpt-", "gemini/", "anthropic/", "openai/")
    is_ollama = not any(model.startswith(p) for p in REMOTE_PREFIXES)
    ollama_model = f"ollama/{model}" if is_ollama and not model.startswith("ollama/") else model

    for i in range(MAX_ITERATIONS):

        # Build kwargs dynamically: Ollama requires api_base; remote models do not.
        # tool_choice="auto" lets the LLM decide whether to call a tool or respond directly.
        kwargs = dict(
            model=ollama_model,
            messages=messages,
            tools=[SSL_PIN_TOOL_SCHEMA],
            tool_choice="auto"
        )
        if is_ollama:
            kwargs["api_base"] = "http://localhost:11434"

        response = litellm.completion(**kwargs)
        message = response.choices[0].message

        # If there are no tool calls, the LLM has produced a final answer — exit the loop.
        if not message.tool_calls:
            return message.content

        # Append the assistant's tool-call message to history before executing.
        # The LLM needs to see its own prior turn when we send the tool result back.
        messages.append(message)

        # Execute every tool the LLM requested (may be more than one in multi-tool scenarios).
        for tool_call in message.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)

            print(f"[Agent] Calling tool: {fn_name} with args: {fn_args}")

            if fn_name in TOOL_REGISTRY:
                result = TOOL_REGISTRY[fn_name](**fn_args)
            else:
                result = {"error": f"Unknown tool: {fn_name}"}

            # Tool results are appended with role="tool" and the matching tool_call_id.
            # The id links this result back to the specific tool call that requested it,
            # which matters when multiple tools are called in parallel.
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": fn_name,
                "content": json.dumps(result)
            })

        # Ollama models (qwen3, qwen2.5-coder, etc.) consistently re-invoke the tool
        # after receiving its result instead of synthesising a final answer.
        # The fix: make one more call *without* tools so the model is forced to respond
        # in plain text. This is scoped to Ollama only — remote models handle it correctly.
        if is_ollama:
            final = litellm.completion(
                model=ollama_model,
                messages=messages,
                api_base="http://localhost:11434"
            )
            return final.choices[0].message.content

    return "Max iterations reached without a final answer."


if __name__ == "__main__":
    import sys
    model = sys.argv[1] if len(sys.argv) > 1 else "gpt-4o"
    user_input = sys.argv[2] if len(sys.argv) > 2 else "Generate SSL pin for https://google.com"

    print(f"\nModel: {model}")
    print(f"Input: {user_input}\n")
    print(run_agent(user_input, model))
