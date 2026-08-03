"""Obtain the local quickstart JWT without printing or committing it."""

import base64
import json
import os
import urllib.request
from pathlib import Path


payload = json.dumps(
    {"email": "admin@open-metadata.org", "password": "YWRtaW4="}
).encode("utf-8")
request = urllib.request.Request(
    "http://127.0.0.1:8585/api/v1/users/login",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=15) as response:
    body = json.load(response)

token = body.get("accessToken") or body.get("token")
if not token:
    raise RuntimeError(f"Login response has no token; keys={sorted(body)}")
token_path = Path(__file__).resolve().parents[3] / "runtime" / "openmetadata-1.13.0" / "admin.jwt"
token_path.parent.mkdir(parents=True, exist_ok=True)
token_path.write_text(token, encoding="utf-8")
os.chmod(token_path, 0o600)
env_path = token_path.with_name("ingestion.env")
env_path.write_text(f"OM_JWT_TOKEN={token}\n", encoding="utf-8")
os.chmod(env_path, 0o600)

claims = {}
try:
    middle = token.split(".")[1]
    middle += "=" * (-len(middle) % 4)
    claims = json.loads(base64.urlsafe_b64decode(middle))
except Exception:
    pass
print(
    json.dumps(
        {
            "token_saved_outside_git": True,
            "token_length": len(token),
            "subject": claims.get("sub"),
            "issuer": claims.get("iss"),
            "token_value_logged": False,
        },
        ensure_ascii=False,
        indent=2,
    )
)
