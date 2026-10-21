"""
JIRVA - OpenRouter API Client (Nemotron)
---------------------------------------------
A thin wrapper around OpenRouter's chat completions endpoint for calling
NVIDIA's Nemotron 3 Nano Omni (free tier). Kept standalone and separate
from the RAG pipeline so it can be tested in isolation first.

Retry/backoff tuning: the free tier's shared capacity pool has been
observed live (this session) both oversubscribed 4x over its stated limit
("Worker local total request limit reached (62/16)") and returning a
non-2xx HTTP 429 directly (a different free model, different failure
shape). Two changes address both:

  1. A flat 8s-per-retry sleep only covered the "200 OK but no 'choices' in
     the body" failure shape - a genuine HTTP-level 429/5xx used to raise
     immediately with zero retries, wasting an otherwise-recoverable
     request. Both shapes are now retried the same way.
  2. The flat 8s delay is replaced with exponential backoff starting at 2s
     (most capacity bursts observed live cleared within a couple seconds -
     an 8s minimum wait was needlessly slow for the common case), capped at
     10s (so a longer outage doesn't balloon retry wait time), plus a small
     random jitter so multiple in-flight requests retrying around the same
     moment don't all wake up in lockstep. Worst case across 4 attempts:
     ~14s of sleep (2+4+8, jitter aside) vs the previous flat 24s (8+8+8).

Usage (standalone test - simple "hello" call, no retrieval involved):
    python openrouter_client.py
"""

import os
import random
import time

import requests
from dotenv import load_dotenv

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
MAX_RETRIES = 4
RETRY_BASE_DELAY_SECONDS = 2
RETRY_MAX_DELAY_SECONDS = 10
RETRY_JITTER_SECONDS = 0.5

# HTTP statuses treated as transient/retryable - genuine capacity/outage
# signals, not something retrying will ever fix for 4xx auth/bad-request
# errors, which still raise immediately (see call_nemotron below).
RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}


def _is_transient_error_message(message):
    return "ResourceExhausted" in message or "rate limit" in message.lower()


def _backoff_delay(attempt):
    """Exponential backoff from RETRY_BASE_DELAY_SECONDS, capped at
    RETRY_MAX_DELAY_SECONDS, plus jitter. `attempt` is the 1-indexed attempt
    number that just failed (delay before attempt+1)."""
    delay = min(RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)), RETRY_MAX_DELAY_SECONDS)
    return delay + random.uniform(0, RETRY_JITTER_SECONDS)


def call_nemotron(messages, max_tokens=1024, temperature=0.3, timeout=60, model=None):
    """
    messages: list of {"role": "system"|"user"|"assistant", "content": str}
    model: optional override of MODEL_NAME - lets a specific call site use a
        different (e.g. faster, non-reasoning) free model without changing
        the default for every caller. Name kept as call_nemotron for
        backwards compatibility even though it can now call other models.
    Returns the model's text response as a string.
    Raises requests.HTTPError on non-retryable API failure, and RuntimeError
    if all retries are exhausted on a transient one - either way, with the
    upstream error message included, so failures are debuggable rather than
    silent.
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
        "model": model or MODEL_NAME,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=timeout)

        if response.ok:
            data = response.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
            # 200 OK but no 'choices' - the free tier's shape for a
            # transient upstream capacity error (see module docstring).
            error_info = data.get("error", {})
            error_message = error_info.get("message", str(data))
            is_transient = _is_transient_error_message(error_message)
        elif response.status_code in RETRYABLE_HTTP_STATUSES:
            error_message = f"HTTP {response.status_code}: {response.text}"
            is_transient = True
        else:
            # Non-transient failure (bad request, auth, etc.) - retrying
            # would just waste time on an error that will never clear.
            raise requests.HTTPError(
                f"OpenRouter API error {response.status_code}: {response.text}"
            )

        last_error = error_message
        if is_transient and attempt < MAX_RETRIES:
            delay = _backoff_delay(attempt)
            print(f"  [RETRY {attempt}/{MAX_RETRIES}] Upstream capacity issue, "
                  f"waiting {delay:.1f}s before retrying: {error_message}")
            time.sleep(delay)
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
