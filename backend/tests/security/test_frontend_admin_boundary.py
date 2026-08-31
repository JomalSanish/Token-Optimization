from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[3] / "frontend"

def test_dashboard_contains_no_admin_credential_or_admin_api_calls():
    app_js = (FRONTEND / "src" / "app.js").read_text(encoding="utf-8")
    index_html = (FRONTEND / "index.html").read_text(encoding="utf-8")

    assert "test_admin_auth_secret_456" not in app_js
    assert "ADMIN_AUTH_SECRET" not in app_js
    assert "/admin/" not in app_js
    assert "test_admin_auth_secret_456" not in index_html

def test_admin_credential_is_entered_at_runtime():
    admin_js = (FRONTEND / "src" / "admin.js").read_text(encoding="utf-8")

    assert "test_admin_auth_secret_456" not in admin_js
    assert "localStorage" not in admin_js
    assert "sessionStorage" not in admin_js
    assert "Authorization: `Bearer ${credential}`" in admin_js
