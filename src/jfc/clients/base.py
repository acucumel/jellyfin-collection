"""Base client with common HTTP functionality."""

from typing import Any, Optional

import httpx
from loguru import logger


class BaseClient:
    """Base HTTP client with common functionality."""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        headers: Optional[dict[str, str]] = None,
    ):
        """
        Initialize base client.

        Args:
            base_url: Base URL for API requests
            api_key: API key for authentication
            timeout: Request timeout in seconds
            headers: Additional headers to include
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._headers = headers or {}
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def headers(self) -> dict[str, str]:
        """Get request headers."""
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **self._headers,
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.headers,
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
        **kwargs,
    ) -> httpx.Response:
        """
        Make HTTP request.

        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            json: JSON body
            **kwargs: Additional httpx arguments

        Returns:
            HTTP response
        """
        client = await self._get_client()

        logger.debug(f"[{self.__class__.__name__}] {method} {endpoint}")

        response = await client.request(
            method=method,
            url=endpoint,
            params=params,
            json=json,
            **kwargs,
        )

        if response.status_code >= 400:
            logger.error(
                f"[{self.__class__.__name__}] {method} {endpoint} "
                f"failed with {response.status_code}: {response.text}"
            )

        return response

    async def get(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
        **kwargs,
    ) -> httpx.Response:
        """Make GET request."""
        return await self._request("GET", endpoint, params=params, **kwargs)

    async def post(
        self,
        endpoint: str,
        json: Optional[dict[str, Any]] = None,
        **kwargs,
    ) -> httpx.Response:
        """Make POST request."""
        return await self._request("POST", endpoint, json=json, **kwargs)

    async def put(
        self,
        endpoint: str,
        json: Optional[dict[str, Any]] = None,
        **kwargs,
    ) -> httpx.Response:
        """Make PUT request."""
        return await self._request("PUT", endpoint, json=json, **kwargs)

    async def delete(
        self,
        endpoint: str,
        **kwargs,
    ) -> httpx.Response:
        """Make DELETE request."""
        return await self._request("DELETE", endpoint, **kwargs)

    async def __aenter__(self) -> "BaseClient":
        """Context manager entry."""
        return self

    async def __aexit__(self, *args) -> None:
        """Context manager exit."""
        await self.close()
