"""Trakt OAuth authentication service."""

import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger
from pydantic import BaseModel


class TraktTokens(BaseModel):
    """Trakt OAuth tokens."""

    access_token: str
    refresh_token: str
    expires_at: datetime
    created_at: datetime
    token_type: str = "Bearer"

    def is_expired(self) -> bool:
        """Check if access token is expired (with 1 hour buffer)."""
        return datetime.now() >= (self.expires_at - timedelta(hours=1))

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "token_type": self.token_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TraktTokens":
        """Create from dict."""
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            token_type=data.get("token_type", "Bearer"),
        )


class TraktAuth:
    """Trakt OAuth authentication handler."""

    OAUTH_URL = "https://api.trakt.tv/oauth"
    TOKEN_FILE = "trakt_tokens.json"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        data_dir: Path,
    ):
        """
        Initialize Trakt auth handler.

        Args:
            client_id: Trakt application client ID
            client_secret: Trakt application client secret
            data_dir: Directory to store token file
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.data_dir = data_dir
        self.token_path = data_dir / self.TOKEN_FILE
        self._tokens: Optional[TraktTokens] = None

    def load_tokens(self) -> Optional[TraktTokens]:
        """Load tokens from file."""
        if not self.token_path.exists():
            logger.debug("No Trakt token file found")
            return None

        try:
            with open(self.token_path, encoding="utf-8") as f:
                data = json.load(f)
            self._tokens = TraktTokens.from_dict(data)
            logger.debug(f"Loaded Trakt tokens (expires: {self._tokens.expires_at})")
            return self._tokens
        except Exception as e:
            logger.warning(f"Failed to load Trakt tokens: {e}")
            return None

    def save_tokens(self, tokens: TraktTokens) -> None:
        """Save tokens to file."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with open(self.token_path, "w", encoding="utf-8") as f:
            json.dump(tokens.to_dict(), f, indent=2)
        self._tokens = tokens
        logger.info(f"Saved Trakt tokens (expires: {tokens.expires_at})")

    def delete_tokens(self) -> None:
        """Delete token file."""
        if self.token_path.exists():
            self.token_path.unlink()
            self._tokens = None
            logger.info("Deleted Trakt tokens")

    async def get_valid_token(self) -> Optional[str]:
        """Get a valid access token, refreshing if needed."""
        tokens = self._tokens or self.load_tokens()

        if not tokens:
            return None

        if tokens.is_expired():
            logger.info("Trakt access token expired, refreshing...")
            tokens = await self.refresh_tokens(tokens.refresh_token)
            if not tokens:
                return None

        return tokens.access_token

    async def device_code_flow(
        self,
        on_code_received: callable = None,
    ) -> Optional[TraktTokens]:
        """
        Perform OAuth Device Code flow.

        Args:
            on_code_received: Callback when user code is received.
                              Receives (user_code, verification_url, expires_in)

        Returns:
            TraktTokens if successful, None otherwise
        """
        async with httpx.AsyncClient() as client:
            # Step 1: Get device code
            logger.info("Requesting Trakt device code...")
            response = await client.post(
                f"{self.OAUTH_URL}/device/code",
                json={"client_id": self.client_id},
            )

            if response.status_code != 200:
                logger.error(f"Failed to get device code: {response.text}")
                return None

            data = response.json()
            device_code = data["device_code"]
            user_code = data["user_code"]
            verification_url = data["verification_url"]
            expires_in = data["expires_in"]
            interval = data["interval"]

            # Notify caller about the code
            if on_code_received:
                on_code_received(user_code, verification_url, expires_in)
            else:
                logger.info(f"Go to: {verification_url}")
                logger.info(f"Enter code: {user_code}")

            # Step 2: Poll for authorization
            start_time = time.time()
            while (time.time() - start_time) < expires_in:
                await asyncio.sleep(interval)

                token_response = await client.post(
                    f"{self.OAUTH_URL}/device/token",
                    json={
                        "code": device_code,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                )

                if token_response.status_code == 200:
                    # Success!
                    token_data = token_response.json()
                    tokens = TraktTokens(
                        access_token=token_data["access_token"],
                        refresh_token=token_data["refresh_token"],
                        expires_at=datetime.now() + timedelta(seconds=token_data["expires_in"]),
                        created_at=datetime.now(),
                    )
                    self.save_tokens(tokens)
                    logger.info("Trakt authentication successful!")
                    return tokens

                elif token_response.status_code == 400:
                    # Handle empty response body
                    try:
                        error_data = token_response.json()
                        error = error_data.get("error", "unknown")
                    except Exception:
                        # Empty body - likely authorization_pending
                        error = "authorization_pending"

                    if error == "authorization_pending":
                        # Still waiting for user
                        continue
                    elif error == "slow_down":
                        interval += 1
                        continue
                    else:
                        logger.error(f"Authorization failed: {error}")
                        return None

                elif token_response.status_code == 410:
                    logger.error("Device code expired")
                    return None

            logger.error("Authorization timed out")
            return None

    async def refresh_tokens(self, refresh_token: str) -> Optional[TraktTokens]:
        """
        Refresh access token using refresh token.

        Args:
            refresh_token: The refresh token

        Returns:
            New TraktTokens if successful, None otherwise
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.OAUTH_URL}/token",
                json={
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                },
            )

            if response.status_code != 200:
                logger.error(f"Failed to refresh Trakt token: {response.text}")
                # Delete invalid tokens
                self.delete_tokens()
                return None

            token_data = response.json()
            tokens = TraktTokens(
                access_token=token_data["access_token"],
                refresh_token=token_data["refresh_token"],
                expires_at=datetime.now() + timedelta(seconds=token_data["expires_in"]),
                created_at=datetime.now(),
            )
            self.save_tokens(tokens)
            logger.info("Trakt tokens refreshed successfully")
            return tokens

    async def revoke_token(self) -> bool:
        """Revoke current access token."""
        tokens = self._tokens or self.load_tokens()
        if not tokens:
            return True

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.OAUTH_URL}/revoke",
                json={
                    "token": tokens.access_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )

            if response.status_code == 200:
                self.delete_tokens()
                logger.info("Trakt token revoked")
                return True
            else:
                logger.warning(f"Failed to revoke token: {response.text}")
                return False
