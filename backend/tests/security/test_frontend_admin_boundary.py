import os
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[3] / "frontend"

def test_dashboard_contains_no_admin_credential():
    # Scan all js/jsx files in frontend/src
    for root, _, files in os.walk(FRONTEND / "src"):
        for f in files:
            if f.endswith((".js", ".jsx")):
                content = (Path(root) / f).read_text(encoding="utf-8")
                assert "test_admin_auth_secret_456" not in content, f"Hardcoded admin secret found in {f}"
                assert "test_app_secret_123" not in content, f"Hardcoded app secret found in {f}"

def test_admin_uses_bearer_token_auth():
    api_js = (FRONTEND / "src" / "services" / "api.js").read_text(encoding="utf-8")
    assert "Authorization" in api_js
    assert "Bearer" in api_js
