"""Shared HTTP client with retry and standard headers."""

import aiohttp
from aiohttp_retry import RetryClient

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def create_http_client(
    user_agent: str = DEFAULT_UA,
    timeout_total: int = 30,
    retry_attempts: int = 3,
) -> RetryClient:
    """Create a shared HTTP client with retry support."""
    timeout = aiohttp.ClientTimeout(total=timeout_total, connect=10)
    connector = aiohttp.TCPConnector(limit=50, limit_per_host=5)

    session = aiohttp.ClientSession(
        timeout=timeout,
        connector=connector,
        headers={"User-Agent": user_agent},
    )

    retry_client = RetryClient(
        client_session=session,
        retry_attempts=retry_attempts,
        retry_for_statuses=[500, 502, 503, 504],
    )
    return retry_client
