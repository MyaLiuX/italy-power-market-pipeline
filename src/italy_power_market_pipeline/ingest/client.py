"""Thin wrapper around entsoe-py: one retry policy for all ENTSO-E requests.
"""

import logging
import time
from collections.abc import Callable
from typing import TypeVar

import requests
from entsoe import EntsoePandasClient
from entsoe.exceptions import NoMatchingDataError

logger = logging.getLogger(__name__)

T = TypeVar("T")

MAX_ATTEMPTS = 4  # one call plus three retries
BASE_DELAY_SECONDS = 2.0  # waits 2s, 4s, 8s between attempts
REQUEST_TIMEOUT_SECONDS = 60  # without a timeout, a stalled request hangs forever


class EntsoeRequestError(Exception):
    """A request that failed for good. Its message never contains the URL."""


def make_client(api_key: str) -> EntsoePandasClient:
    """Build a client with entsoe-py's own retry disabled."""
    return EntsoePandasClient(
        api_key=api_key,
        retry_count=1,  # a single attempt: retries are handled by call_with_retry
        retry_delay=0,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def call_with_retry(request: Callable[[], T], label: str) -> T:
    """Run `request`, retrying transient failures with exponential backoff.

    `label` names the request in log messages, e.g. "prices IT_NORD".
    NoMatchingDataError passes through untouched: it is a real answer.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return request()
        except NoMatchingDataError:
            # The API answered: there is no data. Retrying cannot change that.
            raise
        except requests.RequestException as exc:
            if not _is_transient(exc) or attempt == MAX_ATTEMPTS:
                # The original message contains the request URL, and the URL
                # contains the API key. `from None` keeps it out of tracebacks.
                raise EntsoeRequestError(
                    f"{label}: {_describe(exc)} after {attempt} attempt(s)"
                ) from None
            delay = BASE_DELAY_SECONDS * 2 ** (attempt - 1)
            logger.warning(
                "%s: %s, retry %d of %d in %.0fs",
                label, _describe(exc), attempt, MAX_ATTEMPTS - 1, delay,
            )
            time.sleep(delay)


def _is_transient(exc: requests.RequestException) -> bool:
    """True for failures that may succeed if the same request is sent again."""
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    response = exc.response
    # 429: rate limited. 5xx: server-side failure, including ENTSO-E's 599.
    return response is not None and (
        response.status_code == 429 or response.status_code >= 500
    )


def _describe(exc: requests.RequestException) -> str:
    """Name a failure by type and status code only, never by its message."""
    response = exc.response
    if response is not None:
        return f"{type(exc).__name__} (HTTP {response.status_code})"
    return type(exc).__name__