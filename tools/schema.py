# tools/schema.py

SSL_PIN_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_ssl_pin",
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
                    "description": (
                        "One of: absolute file path to a .pem/.der file, "
                        "a raw PEM certificate string, "
                        "or an HTTPS URL to fetch the cert from."
                    )
                }
            },
            "required": ["cert_input"]
        }
    }
}