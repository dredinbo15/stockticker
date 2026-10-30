"""
Shared HTTP client for SEC EDGAR.

SEC's fair-access policy allows at most 10 requests per second and requires a
descriptive User-Agent. Both the Form 4 and 8-K collectors go through
sec_get() so the limit is respected across them.
"""

import logging
import os
import threading
import time

import requests

logger = logging.getLogger(__name__)

# Stay comfortably below SEC's 10 requests/second ceiling.
_MIN_INTERVAL = 0.12
_lock = threading.Lock()
_last_request = 0.0


def _headers() -> dict:
    # Read at call time so a .env loaded after import is still honoured.
    user_agent = os.getenv("SEC_USER_AGENT", "stockticker contact@example.com")
    return {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}


def _throttle():
    global _last_request
    with _lock:
        wait = _MIN_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def sec_get(url: str, timeout: int = 15, retries: int = 3) -> requests.Response:
    """GET an EDGAR URL with throttling and backoff on 429/5xx responses."""
    for attempt in range(retries):
        _throttle()
        try:
            response = requests.get(url, headers=_headers(), timeout=timeout)
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            logger.warning("SEC request %s failed (%s); retrying.", url, e)
        else:
            if response.status_code != 429 and response.status_code < 500:
                response.raise_for_status()
                return response
            if attempt == retries - 1:
                response.raise_for_status()
            logger.warning("SEC returned %s for %s; backing off.", response.status_code, url)
        time.sleep(2 ** (attempt + 1))
    raise RuntimeError("unreachable")


def raw_document_name(primary_document: str) -> str:
    """Return the raw filing document name for an EDGAR primaryDocument.

    For XML forms such as Form 4, the submissions API lists the XSL-rendered
    view (e.g. 'xslF345X05/form4.xml'), which serves HTML. The raw XML lives
    at the same path without the 'xsl...' directory prefix.
    """
    head, sep, tail = primary_document.partition("/")
    if sep and head.lower().startswith("xsl"):
        return tail
    return primary_document
