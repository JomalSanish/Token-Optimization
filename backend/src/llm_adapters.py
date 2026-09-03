import re
import httpx
from fastapi import HTTPException, status
from typing import Any, Dict, List

class LLMAdapter:
    @staticmethod
    async def call_openai(model_id: str, api_key: str, system_prompt: str, user_prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"}
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )
                if response.status_code != 200:
                    detail = response.json().get("error", {}).get("message", "OpenAI API error")
                    status_code = response.status_code if response.status_code in (401, 429) else 502
                    raise HTTPException(status_code=status_code, detail=f"OpenAI error: {detail}")
                return response.json()["choices"][0]["message"]["content"]
            except httpx.RequestError as e:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"OpenAI service unreachable: {str(e)}"
                )

    @staticmethod
    async def call_anthropic(model_id: str, api_key: str, system_prompt: str, user_prompt: str) -> str:
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": model_id,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 4000,
            "temperature": 0.2
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )
                if response.status_code != 200:
                    detail = response.json().get("error", {}).get("message", "Anthropic API error")
                    status_code = response.status_code if response.status_code in (401, 429) else 502
                    raise HTTPException(status_code=status_code, detail=f"Anthropic error: {detail}")
                return response.json()["content"][0]["text"]
            except httpx.RequestError as e:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Anthropic service unreachable: {str(e)}"
                )

    @staticmethod
    async def call_gemini(model_id: str, api_key: str, system_prompt: str, user_prompt: str) -> str:
        # 1. Clean the model ID string
        clean_model = model_id.strip().lstrip("/").replace("models/", "").strip()
        
        # Fallback to gemini-2.5-flash if the old 1.5 model is passed
        if "1.5" in clean_model:
            clean_model = "gemini-2.5-flash"

        # 2. Must use v1beta and pass key as query parameter
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent"
        params = {"key": api_key.strip()}
        headers = {"Content-Type": "application/json"}
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"System Instruction: {system_prompt}\n\nUser Request: {user_prompt}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json"
            }
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=headers, params=params, json=payload, timeout=60.0)
                if response.status_code != 200:
                    detail = response.json().get("error", {}).get("message", "Gemini API error")
                    status_code = response.status_code if response.status_code in (401, 429) else 502
                    raise HTTPException(status_code=status_code, detail=f"Gemini error: {detail}")
                return response.json()["candidates"][0]["content"]["parts"][0]["text"]
            except httpx.RequestError as e:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Gemini service unreachable: {str(e)}"
                )

    # --- T010: OpenAI-compatible parameterized wrapper ---
    @staticmethod
    async def call_openai_compatible(
        base_url: str,
        model_id: str,
        api_key: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Call any provider that mirrors the OpenAI chat-completions schema.

        Uses the caller-supplied base_url instead of the hardcoded OpenAI URL.
        The request/response shape is identical to call_openai — the base_url
        is the only difference. SSRF validation is performed at provider save
        time (validators.py), not here.
        """
        # Normalise base_url: strip trailing slash so we can append the path cleanly
        endpoint = base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                if response.status_code != 200:
                    detail = response.json().get("error", {}).get("message", "Provider API error")
                    status_code = response.status_code if response.status_code in (401, 429) else 502
                    raise HTTPException(
                        status_code=status_code,
                        detail=f"OpenAI-compatible provider error: {detail}",
                    )
                return response.json()["choices"][0]["message"]["content"]
            except httpx.RequestError as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"OpenAI-compatible provider unreachable: {str(exc)}",
                )


# ---------------------------------------------------------------------------
# T011: Static template substitution helper
# ---------------------------------------------------------------------------
_ALLOWED_TOKENS = {"model_id", "api_key", "system_prompt", "user_prompt"}

def _substitute(template: Any, substitutions: Dict[str, str]) -> Any:
    """Recursively substitute {token} placeholders in a template value.

    Supported input types:
      - str  → str.format_map with the provided substitution dict
      - dict → recursively substitute all values
      - list → recursively substitute all elements
      - Any other type → returned as-is (e.g. int, bool, None)

    Only the four allowed tokens are substituted. Any other {placeholder}
    found in a string is left intact (str.format_map ignores unknown keys
    via the default dict behaviour — but we use a safe mapping that returns
    the literal "{key}" for unknown keys to avoid KeyError).

    IMPORTANT: This function performs only string interpolation — it does NOT
    execute any code, expression, or script found in the template.
    """
    class _SafeMap(dict):
        def __missing__(self, key: str) -> str:
            # Return the literal placeholder unchanged for unknown keys
            return "{" + key + "}"

    if isinstance(template, str):
        return template.format_map(_SafeMap(substitutions))
    if isinstance(template, dict):
        return {k: _substitute(v, substitutions) for k, v in template.items()}
    if isinstance(template, list):
        return [_substitute(item, substitutions) for item in template]
    return template


# ---------------------------------------------------------------------------
# T012: Dot-path extractor for provider responses
# ---------------------------------------------------------------------------
def _extract_path(data: Any, dot_path: str) -> Any:
    """Traverse a nested dict/list using a dot-path string.

    Supports:
      - Simple keys:   "message"
      - Nested keys:   "message.content"
      - Array indexes: "choices[0].message.content"
      - Mixed:         "results[1].items[0].text"

    Returns the value at the path, or raises ValueError if the path
    cannot be followed (key not found, index out of range, or traversing
    a non-dict/non-list node).
    """
    if not dot_path:
        raise ValueError("dot_path must not be empty")

    # Split on dots, but keep array-index notation attached to the key segment
    # e.g. "choices[0].message.content" → ["choices[0]", "message", "content"]
    segments = dot_path.split(".")
    current = data

    for segment in segments:
        # Check for array index notation: key[n]
        index_match = re.fullmatch(r"(.+)\[(\d+)\]", segment)
        if index_match:
            key, idx = index_match.group(1), int(index_match.group(2))
            if not isinstance(current, dict) or key not in current:
                raise ValueError(
                    f"_extract_path: key '{key}' not found in response at path '{dot_path}'"
                )
            current = current[key]
            if not isinstance(current, list) or idx >= len(current):
                raise ValueError(
                    f"_extract_path: index [{idx}] out of range in response at path '{dot_path}'"
                )
            current = current[idx]
        else:
            if not isinstance(current, dict) or segment not in current:
                raise ValueError(
                    f"_extract_path: key '{segment}' not found in response at path '{dot_path}'"
                )
            current = current[segment]

    return current


# ---------------------------------------------------------------------------
# T013: Generic template dispatcher
# ---------------------------------------------------------------------------
async def _dispatch_template(
    adapter_template: Dict[str, Any],
    model_id: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """Dispatch an LLM call using the declarative adapter_template stored in MongoDB.

    Steps:
      1. Build substitution map from the four allowed tokens.
      2. Substitute into header_template and body_template.
      3. POST to request_url using http_method.
      4. On success: extract response text via response_text_path.
      5. On non-2xx: pass through 401/429; map everything else to 502.

    The adapter_template dict shape matches AdapterTemplate schema fields:
      request_url, http_method, header_template, body_template,
      response_text_path, error_message_path.
    """
    subs = {
        "model_id": model_id,
        "api_key": api_key,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
    }

    request_url: str = adapter_template["request_url"]
    http_method: str = adapter_template.get("http_method", "POST").upper()
    header_template: Dict[str, str] = adapter_template.get("header_template", {})
    body_template: Dict[str, Any] = adapter_template.get("body_template", {})
    response_text_path: str = adapter_template["response_text_path"]
    error_message_path: str = adapter_template.get("error_message_path", "")

    # Substitute placeholders (static string interpolation only — no eval/exec)
    resolved_url: str = _substitute(request_url, subs)
    resolved_headers: Dict[str, str] = _substitute(header_template, subs)
    resolved_body: Dict[str, Any] = _substitute(body_template, subs)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                method=http_method,
                url=resolved_url,
                headers=resolved_headers,
                json=resolved_body,
                timeout=30.0,
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Template provider unreachable: {str(exc)}",
            )

    if response.status_code == 200:
        try:
            body = response.json()
            return str(_extract_path(body, response_text_path))
        except (ValueError, KeyError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    f"Template provider returned an unexpected response structure. "
                    f"response_text_path='{response_text_path}' could not be followed: {exc}"
                ),
            )
    else:
        # Attempt to extract the provider's error message via error_message_path
        provider_error: str = "Provider API error"
        if error_message_path:
            try:
                body = response.json()
                provider_error = str(_extract_path(body, error_message_path))
            except Exception:
                pass  # Fall back to the generic message

        # Pass through 401/429; map all other non-2xx to 502
        status_code = response.status_code if response.status_code in (401, 429) else 502
        raise HTTPException(
            status_code=status_code,
            detail=f"Template provider error: {provider_error}",
        )


# ---------------------------------------------------------------------------
# T014: NATIVE_REGISTRY and rewritten dispatch_llm_call (three-way switch)
# ---------------------------------------------------------------------------

# Maps native_key strings (as stored in provider documents) to their
# corresponding static call methods. This dict is developer-controlled and
# fixed at deploy time — admins CANNOT add entries here.
NATIVE_REGISTRY: Dict[str, Any] = {
    "openai": LLMAdapter.call_openai,
    "anthropic": LLMAdapter.call_anthropic,
    "google": LLMAdapter.call_gemini,
}


async def dispatch_llm_call(
    provider_doc: Dict[str, Any],
    model_id: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """Route an LLM call based on the provider document's implementation_type.

    Three-way switch:
      "native"           → look up native_key in NATIVE_REGISTRY and call it
      "openai_compatible" → call_openai_compatible with stored base_url
      "template"         → _dispatch_template with stored adapter_template

    Args:
        provider_doc: The full MongoDB provider document (already fetched by
                      the endpoint from the DB). Must contain 'implementation_type'
                      and the corresponding type-specific fields.
        model_id:     Model identifier to pass to the provider.
        api_key:      User-supplied key (relayed only, never persisted).
        system_prompt: System context for the LLM call.
        user_prompt:   User payload for the LLM call.

    Returns:
        The raw text content returned by the provider.

    Raises:
        HTTPException 400 — unknown implementation_type (shouldn't happen if
                            Pydantic validation is applied at save time).
        HTTPException 500 — known native_key not wired in NATIVE_REGISTRY
                            (developer bug, not a user error).
    """
    impl_type: str = provider_doc.get("implementation_type", "")

    if impl_type == "native":
        native_key: str = provider_doc.get("native_key", "")
        call_fn = NATIVE_REGISTRY.get(native_key)
        if call_fn is None:
            # A native_key that passed Pydantic validation is not wired — developer bug.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Native key '{native_key}' is not wired in NATIVE_REGISTRY. "
                    "This is a backend configuration error."
                ),
            )
        return await call_fn(model_id, api_key, system_prompt, user_prompt)

    elif impl_type == "openai_compatible":
        base_url: str = provider_doc["base_url"]
        return await LLMAdapter.call_openai_compatible(
            base_url, model_id, api_key, system_prompt, user_prompt
        )

    elif impl_type == "template":
        adapter_template: Dict[str, Any] = provider_doc["adapter_template"]
        return await _dispatch_template(
            adapter_template, model_id, api_key, system_prompt, user_prompt
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unknown implementation_type '{impl_type}' on provider "
                f"'{provider_doc.get('provider_id', '?')}'. "
                "Expected one of: native, openai_compatible, template."
            ),
        )

