# tools/schema.py
#
# Defines the tool schema that is passed to the LLM alongside each completion request.
# The schema follows the OpenAI function-calling format, which is also accepted by
# Anthropic (Claude), Google (Gemini), and Ollama via LiteLLM's unified interface.
#
# The LLM reads this schema to understand:
#   - What the tool is called (name)
#   - What it does (description) — this directly affects when the LLM decides to call it
#   - What arguments to pass (parameters) — the LLM fills these in from the user's message
#
# Keeping the schema separate from the implementation lets you tune LLM behaviour
# (by editing descriptions) without touching business logic, and vice versa.

SSL_PIN_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_ssl_pin",

        # The description is the most important field for the LLM.
        # A vague description leads to the tool being called incorrectly or not at all.
        # A precise description tells the LLM exactly when and why to use the tool.
        "description": (
            "Generates the SHA256 SPKI hash of an SSL/TLS public certificate "
            "for use in Android and iOS SSL pinning. "
            "Accepts a file path, raw PEM string, or HTTPS URL."
        ),

        "parameters": {
            "type": "object",
            "properties": {
                "cert_input": {
                    "type": "string",

                    # The parameter description guides the LLM on what value to extract
                    # from the user's message and pass as the argument.
                    "description": (
                        "One of: absolute file path to a .pem/.der file, "
                        "a raw PEM certificate string, "
                        "or an HTTPS URL to fetch the cert from."
                    )
                }
            },
            "required": ["cert_input"]  # LLM must always provide this argument
        }
    }
}
