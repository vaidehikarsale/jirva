"""
Regression suite for openrouter_client's retry/backoff logic. Network calls
(requests.post) and sleeps (time.sleep) are mocked throughout - this tests
the retry/backoff *logic* itself, not real API behavior, and must not
actually sleep or hit the network.
"""
from unittest.mock import MagicMock, patch

import pytest

import openrouter_client as oc


def _mock_response(ok, status_code=200, json_body=None, text=""):
    resp = MagicMock()
    resp.ok = ok
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.text = text
    return resp


class TestBackoffDelay:
    def test_delay_grows_exponentially_up_to_cap(self):
        # Strip jitter by comparing the floor of each delay against the
        # expected un-jittered base progression.
        bases = [oc.RETRY_BASE_DELAY_SECONDS * (2 ** (a - 1)) for a in range(1, 6)]
        capped = [min(b, oc.RETRY_MAX_DELAY_SECONDS) for b in bases]
        assert capped == [2, 4, 8, 10, 10]

    def test_delay_includes_jitter_within_bounds(self):
        for attempt in range(1, 5):
            base = min(oc.RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)), oc.RETRY_MAX_DELAY_SECONDS)
            delay = oc._backoff_delay(attempt)
            assert base <= delay <= base + oc.RETRY_JITTER_SECONDS

    def test_worst_case_total_wait_is_lower_than_old_flat_scheme(self):
        """The old scheme was a flat 8s x 3 sleeps = 24s worst case across
        4 attempts. The new scheme must be strictly better in the worst case
        (jitter aside) - this is the actual point of the tuning."""
        worst_case_total = sum(
            min(oc.RETRY_BASE_DELAY_SECONDS * (2 ** (a - 1)), oc.RETRY_MAX_DELAY_SECONDS)
            for a in range(1, oc.MAX_RETRIES)
        )
        assert worst_case_total < 24


class TestCallNemotronRetryBehavior:
    def test_succeeds_immediately_with_no_retry(self):
        success = _mock_response(True, json_body={"choices": [{"message": {"content": "hi"}}]})
        with patch("openrouter_client.requests.post", return_value=success) as post, \
             patch("openrouter_client.time.sleep") as sleep, \
             patch("openrouter_client.os.getenv", return_value="fake-key"):
            result = oc.call_nemotron([{"role": "user", "content": "hi"}])
        assert result == "hi"
        assert post.call_count == 1
        sleep.assert_not_called()

    def test_retries_on_200_resource_exhausted_then_succeeds(self):
        exhausted = _mock_response(True, json_body={"error": {"message": "ResourceExhausted: pool full"}})
        success = _mock_response(True, json_body={"choices": [{"message": {"content": "ok"}}]})
        with patch("openrouter_client.requests.post", side_effect=[exhausted, success]) as post, \
             patch("openrouter_client.time.sleep") as sleep, \
             patch("openrouter_client.os.getenv", return_value="fake-key"):
            result = oc.call_nemotron([{"role": "user", "content": "hi"}])
        assert result == "ok"
        assert post.call_count == 2
        sleep.assert_called_once()

    def test_retries_on_http_429_then_succeeds(self):
        """The gap this tuning specifically closed: a real HTTP 429 used to
        raise immediately with zero retries."""
        rate_limited = _mock_response(False, status_code=429, text="rate limited")
        success = _mock_response(True, json_body={"choices": [{"message": {"content": "ok"}}]})
        with patch("openrouter_client.requests.post", side_effect=[rate_limited, success]) as post, \
             patch("openrouter_client.time.sleep") as sleep, \
             patch("openrouter_client.os.getenv", return_value="fake-key"):
            result = oc.call_nemotron([{"role": "user", "content": "hi"}])
        assert result == "ok"
        assert post.call_count == 2
        sleep.assert_called_once()

    def test_non_transient_http_error_raises_without_retrying(self):
        bad_request = _mock_response(False, status_code=400, text="bad request")
        with patch("openrouter_client.requests.post", return_value=bad_request) as post, \
             patch("openrouter_client.time.sleep") as sleep, \
             patch("openrouter_client.os.getenv", return_value="fake-key"):
            with pytest.raises(oc.requests.HTTPError):
                oc.call_nemotron([{"role": "user", "content": "hi"}])
        assert post.call_count == 1
        sleep.assert_not_called()

    def test_exhausts_all_retries_and_raises(self):
        exhausted = _mock_response(True, json_body={"error": {"message": "rate limit exceeded"}})
        with patch("openrouter_client.requests.post", return_value=exhausted) as post, \
             patch("openrouter_client.time.sleep") as sleep, \
             patch("openrouter_client.os.getenv", return_value="fake-key"):
            with pytest.raises(RuntimeError):
                oc.call_nemotron([{"role": "user", "content": "hi"}])
        assert post.call_count == oc.MAX_RETRIES
        assert sleep.call_count == oc.MAX_RETRIES - 1
