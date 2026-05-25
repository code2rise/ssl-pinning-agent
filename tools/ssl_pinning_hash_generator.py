# tools/ssl_pin.py
import subprocess
import tempfile
import os
import urllib.request
import ssl

def generate_ssl_pin(cert_input: str) -> dict:
    """
    Accepts:
      - File path to .pem or .der
      - Raw PEM string (starts with -----BEGIN)
      - HTTPS URL (fetches cert automatically)
    
    Returns SHA256 SPKI hash for Android/iOS SSL pinning.
    """
    pem_data = _resolve_input(cert_input)
    
    with tempfile.NamedTemporaryFile(suffix=".pem", delete=False, mode='w') as f:
        f.write(pem_data)
        tmp_path = f.name
    
    try:
        result = subprocess.run(
            f"openssl x509 -in {tmp_path} -pubkey -noout "
            f"| openssl pkey -pubin -outform der "
            f"| openssl dgst -sha256 -binary "
            f"| openssl enc -base64",
            shell=True, capture_output=True, text=True
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip()}
        
        hash_b64 = result.stdout.strip()
        return {
            "sha256_hash": hash_b64
        }
    finally:
        os.unlink(tmp_path)


def _resolve_input(cert_input: str) -> str:
    cert_input = cert_input.strip()
    
    # Raw PEM string
    if cert_input.startswith("-----BEGIN"):
        return cert_input
    
    # HTTPS URL — fetch the cert
    if cert_input.startswith("https://"):
        hostname = cert_input.replace("https://", "").split("/")[0]
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        import socket
        with ctx.wrap_socket(
            socket.create_connection((hostname, 443)),
            server_hostname=hostname
        ) as s:
            der = s.getpeercert(binary_form=True)
        import base64
        pem = "-----BEGIN CERTIFICATE-----\n"
        pem += base64.encodebytes(der).decode()
        pem += "-----END CERTIFICATE-----\n"
        return pem
    
    # File path
    if os.path.exists(cert_input):
        with open(cert_input, 'r') as f:
            return f.read()
    
    raise ValueError(f"Cannot resolve input: {cert_input}")