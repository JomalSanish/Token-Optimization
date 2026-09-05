"""
test_adapters.py — Unit tests for src.llm_adapters and src.validators

Tests run with no network or DB — all IO is stubbed via httpx's AsyncClient
transport parameter or unittest.mock.patch on the exact module-level import name.
These lock down the adapter logic and SSRF guard before any endpoint wires them up.

Coverage:
  - call_openai_compatible: base_url parameterization, no native header leakage
  - _dispatch_template: response_text_path extraction, placeholder substitution,
                         401/429 pass-through, non-2xx → 502 mapping
  - _extract_path: nested dot-path, [n] array-index, error cases
  - _substitute: all four placeholder tokens, unknown tokens left intact,
                 recursive dict/list substitution
  - validate_provider_url: HTTPS-only, loopback, private, link-local SSRF rejection

Patching strategy:
  - httpx.AsyncClient is stubbed by passing a custom transport= to a real AsyncClient.
    The adapter under test uses `async with httpx.AsyncClient() as client:`, so we
    patch `src.llm_adapters.httpx.AsyncClient` to a factory that injects our transport.
  - socket.getaddrinfo is patched via `unittest.mock.patch("src.validators.socket.getaddrinfo")`.
"""
import json
import socket
import pytest
import httpx
from decimal import Decimal
from unittest.mock import patch as mock_patch
from fastapi import HTTPException

from src.llm_adapters import (
    LLMAdapter,
    _substitute,
    _extract_path,
    _dispatch_template,
    dispatch_llm_call,
    NATIVE_REGISTRY,
)
from src.validators import validate_provider_url


# ---------------------------------------------------------------------------
# Helpers — HTTPX transport stubs and factory
# ---------------------------------------------------------------------------

class _MockTransport(httpx.AsyncBaseTransport):
    """In-process transport returning a fixed response."""

    def __init__(self, status_code: int, body: dict | str):
        self._status_code = status_code
        if isinstance(body, dict):
            self._content = json.dumps(body).encode()
        else:
            self._content = body.encode() if isinstance(body, str) else body

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=self._status_code,
            headers={"Content-Type": "application/json"},
            content=self._content,
            request=request,
        )


class _CapturingTransport(httpx.AsyncBaseTransport):
    """Captures request details and returns a fixed 200 response."""

    def __init__(self, response_body: dict):
        self._response_body = response_body
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            status_code=200,
            headers={"Content-Type": "application/json"},
            content=json.dumps(self._response_body).encode(),
            request=request,
        )


class _RaisingTransport(httpx.AsyncBaseTransport):
    """Simulates a network-level failure (DNS/connect/timeout) by raising
    an httpx.RequestError subclass instead of returning a response."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)


def _make_client_factory(transport: httpx.AsyncBaseTransport):
    """Return a factory that produces an httpx.AsyncClient pre-wired with *transport*.

    We patch `src.llm_adapters.httpx.AsyncClient` with this factory so that
    `httpx.AsyncClient()` calls inside the adapter receive our stub transport
    without the lambda → recursive-call problem.
    """
    real_client_class = httpx.AsyncClient

    class _PatchedAsyncClient(real_client_class):
        def __init__(self, **kwargs):
            kwargs["transport"] = transport
            super().__init__(**kwargs)

    return _PatchedAsyncClient


def _openai_shape(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


def _cohere_shape(text: str) -> dict:
    return {"message": {"content": [{"type": "text", "text": text}]}}


# ---------------------------------------------------------------------------
# T010 — call_openai_compatible
# ---------------------------------------------------------------------------

class TestCallOpenAICompatible:
    @pytest.mark.asyncio
    async def test_uses_supplied_base_url(self, monkeypatch):
        """Confirms request goes to base_url/chat/completions, not the hardcoded OpenAI URL."""
        transport = _CapturingTransport(_openai_shape("hello"))
        monkeypatch.setattr(
            "src.llm_adapters.httpx.AsyncClient",
            _make_client_factory(transport),
        )

        result = await LLMAdapter.call_openai_compatible(
            base_url="https://api.deepseek.com/v1",
            model_id="deepseek-chat",
            api_key="sk-test",
            system_prompt="sys",
            user_prompt="hi",
        )

        assert result == "hello"
        assert len(transport.requests) == 1
        url = str(transport.requests[0].url)
        assert "deepseek.com" in url
        assert "openai.com" not in url
        assert url.endswith("/chat/completions")

    @pytest.mark.asyncio
    async def test_strips_trailing_slash_from_base_url(self, monkeypatch):
        transport = _CapturingTransport(_openai_shape("ok"))
        monkeypatch.setattr("src.llm_adapters.httpx.AsyncClient",
                            _make_client_factory(transport))

        await LLMAdapter.call_openai_compatible(
            base_url="https://api.example.com/v1/",  # trailing slash
            model_id="m",
            api_key="key",
            system_prompt="s",
            user_prompt="u",
        )
        url = str(transport.requests[0].url)
        assert url.endswith("/chat/completions")
        # Ensure no double-slash in the path portion
        path_part = url.split("://", 1)[1]
        assert "//" not in path_part

    @pytest.mark.asyncio
    async def test_passthrough_401(self, monkeypatch):
        transport = _MockTransport(401, {"error": {"message": "bad key"}})
        monkeypatch.setattr("src.llm_adapters.httpx.AsyncClient",
                            _make_client_factory(transport))
        with pytest.raises(HTTPException) as exc:
            await LLMAdapter.call_openai_compatible(
                "https://api.example.com/v1", "m", "key", "s", "u"
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_passthrough_429(self, monkeypatch):
        transport = _MockTransport(429, {"error": {"message": "rate limit"}})
        monkeypatch.setattr("src.llm_adapters.httpx.AsyncClient",
                            _make_client_factory(transport))
        with pytest.raises(HTTPException) as exc:
            await LLMAdapter.call_openai_compatible(
                "https://api.example.com/v1", "m", "key", "s", "u"
            )
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_non_2xx_maps_to_502(self, monkeypatch):
        transport = _MockTransport(503, {})
        monkeypatch.setattr("src.llm_adapters.httpx.AsyncClient",
                            _make_client_factory(transport))
        with pytest.raises(HTTPException) as exc:
            await LLMAdapter.call_openai_compatible(
                "https://api.example.com/v1", "m", "key", "s", "u"
            )
        assert exc.value.status_code == 502

    @pytest.mark.asyncio
    async def test_network_error_maps_to_502(self, monkeypatch):
        """A connection-level failure (no response at all) must also map to 502."""
        monkeypatch.setattr("src.llm_adapters.httpx.AsyncClient",
                            _make_client_factory(_RaisingTransport()))
        with pytest.raises(HTTPException) as exc:
            await LLMAdapter.call_openai_compatible(
                "https://api.example.com/v1", "m", "key", "s", "u"
            )
        assert exc.value.status_code == 502
        assert "unreachable" in exc.value.detail

    @pytest.mark.asyncio
    async def test_no_native_provider_assumptions(self, monkeypatch):
        """No anthropic-version, x-api-key headers — only Bearer auth."""
        transport = _CapturingTransport(_openai_shape("ok"))
        monkeypatch.setattr("src.llm_adapters.httpx.AsyncClient",
                            _make_client_factory(transport))

        await LLMAdapter.call_openai_compatible(
            "https://api.example.com/v1", "m", "sk-xyz", "s", "u"
        )

        headers = dict(transport.requests[0].headers)
        assert "anthropic-version" not in headers
        assert "x-api-key" not in headers
        assert headers.get("authorization", "").startswith("Bearer ")


# ---------------------------------------------------------------------------
# T011 — _substitute
# ---------------------------------------------------------------------------

class TestSubstitute:
    def test_all_four_tokens_in_string(self):
        tmpl = "{model_id}|{api_key}|{system_prompt}|{user_prompt}"
        result = _substitute(tmpl, {
            "model_id": "gpt-4o",
            "api_key": "sk-123",
            "system_prompt": "SYS",
            "user_prompt": "USR",
        })
        assert result == "gpt-4o|sk-123|SYS|USR"

    def test_unknown_token_left_intact(self):
        tmpl = "hello {unknown_token} world"
        result = _substitute(tmpl, {"model_id": "m"})
        assert result == "hello {unknown_token} world"

    def test_recursive_dict(self):
        tmpl = {
            "Authorization": "Bearer {api_key}",
            "X-Model": "{model_id}",
        }
        result = _substitute(tmpl, {"api_key": "KEY", "model_id": "MODEL"})
        assert result == {"Authorization": "Bearer KEY", "X-Model": "MODEL"}

    def test_recursive_list(self):
        tmpl = ["{system_prompt}", "{user_prompt}"]
        result = _substitute(tmpl, {"system_prompt": "SYS", "user_prompt": "USR"})
        assert result == ["SYS", "USR"]

    def test_nested_dict_in_list(self):
        tmpl = [{"role": "system", "content": "{system_prompt}"},
                {"role": "user",   "content": "{user_prompt}"}]
        result = _substitute(tmpl, {"system_prompt": "S", "user_prompt": "U"})
        assert result == [{"role": "system", "content": "S"},
                          {"role": "user", "content": "U"}]

    def test_non_string_values_unchanged(self):
        tmpl = {"count": 42, "flag": True, "val": None}
        result = _substitute(tmpl, {"model_id": "m"})
        assert result == {"count": 42, "flag": True, "val": None}

    def test_partial_substitution(self):
        tmpl = "Model: {model_id}, Prompt: {user_prompt}"
        result = _substitute(tmpl, {"model_id": "gpt-4o", "user_prompt": "hello"})
        assert result == "Model: gpt-4o, Prompt: hello"

    def test_empty_substitutions(self):
        tmpl = "no placeholders here"
        result = _substitute(tmpl, {})
        assert result == "no placeholders here"


# ---------------------------------------------------------------------------
# T012 — _extract_path
# ---------------------------------------------------------------------------

class TestExtractPath:
    def test_simple_key(self):
        assert _extract_path({"text": "hello"}, "text") == "hello"

    def test_nested_dot_path(self):
        data = {"message": {"content": "hi"}}
        assert _extract_path(data, "message.content") == "hi"

    def test_array_index(self):
        data = {"choices": [{"message": {"content": "out"}}]}
        assert _extract_path(data, "choices[0].message.content") == "out"

    def test_array_index_second_element(self):
        data = {"items": ["a", "b", "c"]}
        assert _extract_path(data, "items[1]") == "b"

    def test_deep_nested_with_array(self):
        data = {"results": [{"items": [{"text": "found"}]}]}
        assert _extract_path(data, "results[0].items[0].text") == "found"

    def test_missing_key_raises(self):
        with pytest.raises(ValueError, match="not found"):
            _extract_path({"a": 1}, "b")

    def test_index_out_of_range_raises(self):
        with pytest.raises(ValueError, match="out of range"):
            _extract_path({"choices": []}, "choices[0]")

    def test_missing_key_before_bracket_raises(self):
        """The key preceding [n] is absent entirely (not just an empty list)."""
        with pytest.raises(ValueError, match="not found"):
            _extract_path({}, "choices[0]")

    def test_empty_dot_path_raises(self):
        with pytest.raises(ValueError, match="empty"):
            _extract_path({}, "")

    def test_cohere_style_path(self):
        data = {"message": {"content": [{"type": "text", "text": "response"}]}}
        assert _extract_path(data, "message.content[0].text") == "response"


# ---------------------------------------------------------------------------
# T013 — _dispatch_template
# ---------------------------------------------------------------------------

class TestDispatchTemplate:
    def _make_template(
        self,
        response_text_path: str = "choices[0].message.content",
        error_message_path: str = "error.message",
    ) -> dict:
        return {
            "request_url": "https://api.example.com/v1/chat",
            "http_method": "POST",
            "header_template": {"Authorization": "Bearer {api_key}"},
            "body_template": {
                "model": "{model_id}",
                "messages": [{"role": "user", "content": "{user_prompt}"}],
            },
            "response_text_path": response_text_path,
            "error_message_path": error_message_path,
        }

    @pytest.mark.asyncio
    async def test_successful_extraction_via_response_text_path(self, monkeypatch):
        payload = {"choices": [{"message": {"content": "template-response"}}]}
        transport = _MockTransport(200, payload)
        monkeypatch.setattr("src.llm_adapters.httpx.AsyncClient",
                            _make_client_factory(transport))
        result = await _dispatch_template(
            self._make_template(), "m1", "sk-key", "SYS", "USR"
        )
        assert result == "template-response"

    @pytest.mark.asyncio
    async def test_placeholders_substituted(self, monkeypatch):
        """model_id, api_key, user_prompt all appear in the outgoing request."""
        transport = _CapturingTransport({"choices": [{"message": {"content": "ok"}}]})
        monkeypatch.setattr("src.llm_adapters.httpx.AsyncClient",
                            _make_client_factory(transport))

        await _dispatch_template(
            self._make_template(),
            model_id="my-model",
            api_key="my-key",
            system_prompt="sys-text",
            user_prompt="usr-text",
        )
        req = transport.requests[0]
        body = json.loads(req.content)
        assert body["model"] == "my-model"
        assert body["messages"][0]["content"] == "usr-text"
        assert req.headers.get("authorization") == "Bearer my-key"

    @pytest.mark.asyncio
    async def test_novel_rest_shape_via_response_text_path(self, monkeypatch):
        """Any response shape works as long as response_text_path matches."""
        template = self._make_template(response_text_path="message.content[0].text")
        transport = _MockTransport(200, _cohere_shape("cohere-reply"))
        monkeypatch.setattr("src.llm_adapters.httpx.AsyncClient",
                            _make_client_factory(transport))
        result = await _dispatch_template(template, "command-r", "ck", "SYS", "USR")
        assert result == "cohere-reply"

    @pytest.mark.asyncio
    async def test_passthrough_401(self, monkeypatch):
        transport = _MockTransport(401, {"error": {"message": "unauth"}})
        monkeypatch.setattr("src.llm_adapters.httpx.AsyncClient",
                            _make_client_factory(transport))
        with pytest.raises(HTTPException) as exc:
            await _dispatch_template(self._make_template(), "m", "k", "s", "u")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_passthrough_429(self, monkeypatch):
        transport = _MockTransport(429, {"error": {"message": "rate"}})
        monkeypatch.setattr("src.llm_adapters.httpx.AsyncClient",
                            _make_client_factory(transport))
        with pytest.raises(HTTPException) as exc:
            await _dispatch_template(self._make_template(), "m", "k", "s", "u")
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_other_non_2xx_maps_to_502(self, monkeypatch):
        transport = _MockTransport(500, {})
        monkeypatch.setattr("src.llm_adapters.httpx.AsyncClient",
                            _make_client_factory(transport))
        with pytest.raises(HTTPException) as exc:
            await _dispatch_template(self._make_template(), "m", "k", "s", "u")
        assert exc.value.status_code == 502

    @pytest.mark.asyncio
    async def test_network_error_maps_to_502(self, monkeypatch):
        """A connection-level failure (no response at all) must also map to 502."""
        monkeypatch.setattr("src.llm_adapters.httpx.AsyncClient",
                            _make_client_factory(_RaisingTransport()))
        with pytest.raises(HTTPException) as exc:
            await _dispatch_template(self._make_template(), "m", "k", "s", "u")
        assert exc.value.status_code == 502
        assert "unreachable" in exc.value.detail

    @pytest.mark.asyncio
    async def test_bad_response_text_path_raises_502(self, monkeypatch):
        """If the response JSON doesn't match response_text_path → 502."""
        template = self._make_template(response_text_path="nonexistent.key")
        transport = _MockTransport(200, {"something": "else"})
        monkeypatch.setattr("src.llm_adapters.httpx.AsyncClient",
                            _make_client_factory(transport))
        with pytest.raises(HTTPException) as exc:
            await _dispatch_template(template, "m", "k", "s", "u")
        assert exc.value.status_code == 502

    @pytest.mark.asyncio
    async def test_no_native_provider_assumptions_in_template_path(self, monkeypatch):
        """Template dispatch must not inject native-provider-specific fields."""
        transport = _CapturingTransport({"choices": [{"message": {"content": "ok"}}]})
        monkeypatch.setattr("src.llm_adapters.httpx.AsyncClient",
                            _make_client_factory(transport))

        await _dispatch_template(self._make_template(), "m", "sk", "s", "u")

        req = transport.requests[0]
        headers = dict(req.headers)
        body = json.loads(req.content)

        assert "anthropic-version" not in headers
        assert "x-api-key" not in headers
        assert "candidates" not in body
        assert "generationConfig" not in body


# ---------------------------------------------------------------------------
# T014 — dispatch_llm_call (three-way switch)
# ---------------------------------------------------------------------------

class TestDispatchLlmCall:
    @pytest.mark.asyncio
    async def test_native_type_calls_registered_function(self, monkeypatch):
        """implementation_type='native' must look up native_key in NATIVE_REGISTRY
        and call the registered function with the same positional args."""
        calls = []

        async def _stub_native(model_id, api_key, system_prompt, user_prompt):
            calls.append((model_id, api_key, system_prompt, user_prompt))
            return "native-result"

        monkeypatch.setitem(NATIVE_REGISTRY, "stub-native", _stub_native)

        provider_doc = {
            "implementation_type": "native",
            "native_key": "stub-native",
            "provider_id": "stubprovider",
        }
        result = await dispatch_llm_call(provider_doc, "m1", "key1", "sys", "usr")

        assert result == "native-result"
        assert calls == [("m1", "key1", "sys", "usr")]

    @pytest.mark.asyncio
    async def test_native_type_unwired_key_raises_500(self):
        """A native_key that isn't present in NATIVE_REGISTRY is a backend
        configuration bug (should never happen if Pydantic validation ran
        at save time), and must surface as a 500, not a silent failure."""
        provider_doc = {
            "implementation_type": "native",
            "native_key": "not-a-real-key",
            "provider_id": "brokenprovider",
        }
        with pytest.raises(HTTPException) as exc:
            await dispatch_llm_call(provider_doc, "m", "k", "s", "u")
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_openai_compatible_type_uses_stored_base_url(self, monkeypatch):
        transport = _CapturingTransport(_openai_shape("compat-result"))
        monkeypatch.setattr("src.llm_adapters.httpx.AsyncClient",
                            _make_client_factory(transport))

        provider_doc = {
            "implementation_type": "openai_compatible",
            "base_url": "https://api.deepseek.com/v1",
            "provider_id": "deepseek",
        }
        result = await dispatch_llm_call(provider_doc, "deepseek-chat", "sk", "sys", "usr")

        assert result == "compat-result"
        assert "deepseek.com" in str(transport.requests[0].url)

    @pytest.mark.asyncio
    async def test_template_type_uses_stored_adapter_template(self, monkeypatch):
        transport = _MockTransport(200, {"choices": [{"message": {"content": "tmpl-result"}}]})
        monkeypatch.setattr("src.llm_adapters.httpx.AsyncClient",
                            _make_client_factory(transport))

        provider_doc = {
            "implementation_type": "template",
            "provider_id": "customprovider",
            "adapter_template": {
                "request_url": "https://api.custom.com/v1/chat",
                "http_method": "POST",
                "header_template": {"Authorization": "Bearer {api_key}"},
                "body_template": {"model": "{model_id}"},
                "response_text_path": "choices[0].message.content",
                "error_message_path": "error.message",
            },
        }
        result = await dispatch_llm_call(provider_doc, "custom-model", "ck", "sys", "usr")

        assert result == "tmpl-result"

    @pytest.mark.asyncio
    async def test_unknown_implementation_type_raises_400(self):
        provider_doc = {
            "implementation_type": "carrier-pigeon",
            "provider_id": "weirdprovider",
        }
        with pytest.raises(HTTPException) as exc:
            await dispatch_llm_call(provider_doc, "m", "k", "s", "u")
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# T009 — validate_provider_url (SSRF guard)
# ---------------------------------------------------------------------------

def _fake_getaddrinfo_public(host, port, *a, **kw):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]


def _fake_getaddrinfo_loopback(host, port, *a, **kw):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0))]


def _fake_getaddrinfo_fail(host, port, *a, **kw):
    raise socket.gaierror("Name or service not known")


def _fake_getaddrinfo_empty(host, port, *a, **kw):
    return []


def _fake_getaddrinfo_multicast(host, port, *a, **kw):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("224.0.0.1", 0))]


def _fake_getaddrinfo_reserved(host, port, *a, **kw):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("240.0.0.1", 0))]


def _fake_getaddrinfo_unspecified(host, port, *a, **kw):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("0.0.0.0", 0))]


def _fake_getaddrinfo_unparseable(host, port, *a, **kw):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("not-an-ip", 0))]


class TestValidateProviderUrl:
    def test_valid_https_url_passes(self):
        with mock_patch("src.validators.socket.getaddrinfo",
                        side_effect=_fake_getaddrinfo_public):
            # Should not raise
            validate_provider_url("https://api.example.com/v1")

    def test_http_scheme_rejected(self):
        with pytest.raises(ValueError, match="https"):
            validate_provider_url("http://api.example.com/v1")

    def test_ftp_scheme_rejected(self):
        with pytest.raises(ValueError, match="https"):
            validate_provider_url("ftp://api.example.com/v1")

    def test_no_scheme_rejected(self):
        # urlparse puts everything into path when no scheme; hostname → None → ValueError
        with pytest.raises(ValueError):
            validate_provider_url("api.example.com/v1")

    def test_empty_string_rejected(self):
        with pytest.raises(ValueError):
            validate_provider_url("")

    def test_loopback_ipv4_rejected(self):
        with pytest.raises(ValueError, match="loopback"):
            validate_provider_url("https://127.0.0.1/v1")

    def test_loopback_hostname_rejected(self):
        with mock_patch("src.validators.socket.getaddrinfo",
                        side_effect=_fake_getaddrinfo_loopback):
            with pytest.raises(ValueError, match="loopback"):
                validate_provider_url("https://localhost/v1")

    def test_private_rfc1918_class_a_rejected(self):
        with pytest.raises(ValueError, match="private"):
            validate_provider_url("https://10.0.0.1/v1")

    def test_private_rfc1918_class_b_rejected(self):
        with pytest.raises(ValueError, match="private"):
            validate_provider_url("https://172.16.0.1/v1")

    def test_private_rfc1918_class_c_rejected(self):
        with pytest.raises(ValueError, match="private"):
            validate_provider_url("https://192.168.1.100/v1")

    def test_link_local_rejected(self):
        with pytest.raises(ValueError, match="link-local"):
            validate_provider_url("https://169.254.1.1/v1")

    def test_dns_failure_rejected(self):
        with mock_patch("src.validators.socket.getaddrinfo",
                        side_effect=_fake_getaddrinfo_fail):
            with pytest.raises(ValueError, match="could not be resolved"):
                validate_provider_url("https://this-domain-does-not-exist.invalid/v1")

    def test_no_hostname_rejected(self):
        # A scheme-relative-looking URL with an empty netloc has no hostname.
        with pytest.raises(ValueError, match="hostname"):
            validate_provider_url("https:///v1")

    def test_empty_dns_results_rejected(self):
        with mock_patch("src.validators.socket.getaddrinfo",
                        side_effect=_fake_getaddrinfo_empty):
            with pytest.raises(ValueError, match="no addresses"):
                validate_provider_url("https://api.example.com/v1")

    def test_multicast_rejected(self):
        with mock_patch("src.validators.socket.getaddrinfo",
                        side_effect=_fake_getaddrinfo_multicast):
            with pytest.raises(ValueError, match="multicast"):
                validate_provider_url("https://api.example.com/v1")

    def test_reserved_rejected(self):
        with mock_patch("src.validators.socket.getaddrinfo",
                        side_effect=_fake_getaddrinfo_reserved):
            with pytest.raises(ValueError, match="reserved"):
                validate_provider_url("https://api.example.com/v1")

    def test_unspecified_rejected(self):
        """After reordering validators.py to check narrow categories before the
        broad is_private catch-all, 0.0.0.0 now correctly surfaces the specific
        "unspecified" message instead of being masked by "private"."""
        with mock_patch("src.validators.socket.getaddrinfo",
                        side_effect=_fake_getaddrinfo_unspecified):
            with pytest.raises(ValueError, match="unspecified"):
                validate_provider_url("https://api.example.com/v1")

    def test_unparseable_address_rejected(self):
        with mock_patch("src.validators.socket.getaddrinfo",
                        side_effect=_fake_getaddrinfo_unparseable):
            with pytest.raises(ValueError, match="unparseable"):
                validate_provider_url("https://api.example.com/v1")
