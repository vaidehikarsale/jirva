"""
JIRVA - OpenRouter API Client (Nemotron)
---------------------------------------------
A thin wrapper around OpenRouter's chat completions endpoint for calling
NVIDIA's Nemotron 3 Nano Omni (free tier). Kept standalone and separate
from the RAG pipeline so it can be tested in isolation first.

Usage (standalone test - simple "hello" call, no retrieval involved):
    python openrouter_client.py
"""

import os
import time

import requests
from dotenv import load_dotenv

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
MAX_RETRIES = 4
RETRY_DELAY_SECONDS = 8  # free-tier capacity errors are usually transient and clear within seconds


def call_nemotron(messages, max_tokens=1024, temperature=0.3, timeout=60):
    """
    messages: list of {"role": "system"|"user"|"assistant", "content": str}
    Returns the model's text response as a string.
    Raises requests.HTTPError on API failure, with the response body included
    in the error where possible, so failures are debuggable rather than silent.
    """
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not found - check your .env file")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=timeout)

        if not response.ok:
            raise requests.HTTPError(
                f"OpenRouter API error {response.status_code}: {response.text}"
            )

        data = response.json()

        if "choices" in data:
            return data["choices"][0]["message"]["content"]

        # No 'choices' but a 200 response - likely a transient upstream capacity error
        error_info = data.get("error", {})
        error_message = error_info.get("message", str(data))
        last_error = error_message

        is_transient = "ResourceExhausted" in error_message or "rate limit" in error_message.lower()
        if is_transient and attempt < MAX_RETRIES:
            print(f"  [RETRY {attempt}/{MAX_RETRIES}] Upstream capacity issue, "
                  f"waiting {RETRY_DELAY_SECONDS}s before retrying: {error_message}")
            time.sleep(RETRY_DELAY_SECONDS)
            continue
        else:
            raise RuntimeError(f"OpenRouter call failed after {attempt} attempt(s): {error_message}")

    raise RuntimeError(f"OpenRouter call failed after {MAX_RETRIES} attempts: {last_error}")


def main():
    """Simple end-to-end test: no retrieval, no evidence - just confirm the
    API call itself works before wiring anything else in."""
    print(f"Testing OpenRouter API call to {MODEL_NAME} ...")
    messages = [
        {"role": "user", "content": "Say hello in one sentence, and confirm you are Nemotron."}
    ]
    try:
        result = call_nemotron(messages)
        print("\n--- SUCCESS ---")
        print("Model response:")
        print(result)
    except Exception as e:
        print("\n--- FAILED ---")
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
