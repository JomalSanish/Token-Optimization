import httpx
from fastapi import HTTPException, status
from typing import Dict, Any, List

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

async def dispatch_llm_call(
    provider: str,
    model_id: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str
) -> str:
    """Dispatches the call to the selected provider adapter."""
    p_lower = provider.lower()
    if p_lower == "openai":
        return await LLMAdapter.call_openai(model_id, api_key, system_prompt, user_prompt)
    elif p_lower == "anthropic":
        return await LLMAdapter.call_anthropic(model_id, api_key, system_prompt, user_prompt)
    elif p_lower == "google" or p_lower == "gemini":
        return await LLMAdapter.call_gemini(model_id, api_key, system_prompt, user_prompt)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider: '{provider}'."
        )
