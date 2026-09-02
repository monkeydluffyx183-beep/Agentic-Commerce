"""
Shopify token management

Handles OAuth client-credentials grant, token caching, and automatic refresh.
Shopify stopped issuing non-expiring tokens for custom apps in January 2026.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from ..core.errors import ConfigurationError, ShopifyError


@dataclass
class TokenInfo:
    """Cached token information"""
    access_token: str
    expires_at: float  # Unix timestamp
    created_at: float = field(default_factory=time.time)
    
    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at
    
    @property
    def should_refresh(self) -> bool:
        """Refresh 5 minutes before expiry"""
        return time.time() >= (self.expires_at - 300)


class TokenManager:
    """
    Manages Shopify OAuth tokens
    
    Uses client-credentials grant to mint tokens from SHOPIFY_CLIENT_ID/SHOPIFY_CLIENT_SECRET.
    Tokens last about 24 hours; we refresh 5 minutes before expiry.
    If a request is rejected with 401, we re-mint once automatically.
    
    Prerequisites:
    - App and store must belong to the same Shopify organization
    - Store must be created from Dev Dashboard's "Dev stores" page
    """
    
    def __init__(
        self,
        shop_domain: str,
        client_id: str,
        client_secret: str,
        pinned_token: Optional[str] = None,
    ):
        self.shop_domain = shop_domain
        self.client_id = client_id
        self.client_secret = client_secret
        self.pinned_token = pinned_token
        
        self._token: Optional[TokenInfo] = None
        self._lock = asyncio.Lock()
        
        # If pinned token provided, use it without expiry (never refreshed)
        if pinned_token:
            self._token = TokenInfo(
                access_token=pinned_token,
                expires_at=float("inf"),
            )
    
    async def get_token(self) -> str:
        """Get valid access token, refreshing if needed"""
        if self.pinned_token:
            return self.pinned_token
        
        async with self._lock:
            if self._token and not self._token.should_refresh:
                return self._token.access_token
            
            await self._mint_token()
            return self._token.access_token
    
    async def _mint_token(self) -> None:
        """Mint new token via client-credentials grant"""
        url = f"https://{self.shop_domain}/admin/oauth/access_token"
        
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                # Shopify returns access_token and expires_in (seconds)
                access_token = data["access_token"]
                expires_in = data.get("expires_in", 86400)  # Default 24 hours
                
                self._token = TokenInfo(
                    access_token=access_token,
                    expires_at=time.time() + expires_in,
                )
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    raise ConfigurationError(
                        "Shopify client-credentials grant failed. "
                        "Ensure app and store belong to the same Shopify organization.",
                        missing_var="SHOPIFY_CLIENT_ID/SHOPIFY_CLIENT_SECRET",
                    )
                raise ShopifyError(
                    f"Failed to mint Shopify token: {e}",
                    status_code=e.response.status_code,
                )
            except httpx.RequestError as e:
                raise ShopifyError(f"Network error minting Shopify token: {e}")
            except KeyError as e:
                raise ShopifyError(f"Invalid Shopify token response: missing {e}")
    
    async def invalidate(self) -> None:
        """Invalidate cached token (force re-mint on next use)"""
        if self.pinned_token:
            return  # Can't invalidate pinned token
        async with self._lock:
            self._token = None
