# agent.py
import json
import litellm
from tools.ssl_pinning_hash_generator import generate_ssl_pin
from tools.schema import SSL_PIN_TOOL_SCHEMA

# Map tool names to actual functions
TOOL_REGISTRY = {
    "generate_ssl_pin": generate_ssl_pin
}

def run_agent(user_input: str, model: str) -> str:
    """
    model examples:
      "claude-sonnet-4-6"
      "gemini/gemini-1.5-pro"
      "gpt-4o"
      "ollama/qwen2.5-coder"  ← your local model
    """
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
    
    MAX_ITERATIONS = 5

    REMOTE_PREFIXES = ("claude-", "gpt-", "gemini/", "anthropic/", "openai/")
    is_ollama = not any(model.startswith(p) for p in REMOTE_PREFIXES)
    ollama_model = f"ollama/{model}" if is_ollama and not model.startswith("ollama/") else model

    for i in range(MAX_ITERATIONS):
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
        
        # LLM is done — no tool call
        if not message.tool_calls:
            return message.content

        # Append assistant message (with tool call) to history
        messages.append(message)

        # Execute each tool call
        for tool_call in message.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)

            print(f"[Agent] Calling tool: {fn_name} with args: {fn_args}")

            if fn_name in TOOL_REGISTRY:
                result = TOOL_REGISTRY[fn_name](**fn_args)
            else:
                result = {"error": f"Unknown tool: {fn_name}"}

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": fn_name,
                "content": json.dumps(result)
            })

        # Ollama models don't reliably exit the tool loop on their own;
        # force a final text response by omitting tools entirely
        if ollama_model.startswith("ollama/"):
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