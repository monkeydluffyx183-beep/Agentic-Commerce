"""
Protocol definitions for Shopify and Razorpay ports

These protocols define the interface that concrete implementations must satisfy.
The SDK depends only on these abstractions, not on specific implementations.
"""

from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class ShopifyPort(Protocol):
    """
    Shopify Admin API GraphQL client interface
    
    This protocol defines all operations the SDK needs from Shopify.
    Implementations can be:
    - RealShopifyClient: Uses GraphQL Admin API with OAuth tokens
    - DemoShopifyClient: Returns dynamically generated demo data (Faker-backed)
    """
    
    async def search_products(
        self,
        merchant_id: UUID,
        query: str | None = None,
        max_price: Decimal | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Search products in catalog"""
        ...
    
    async def get_product(self, merchant_id: UUID, product_id: str) -> dict:
        """Get product by ID"""
        ...
    
    async def get_inventory(
        self,
        merchant_id: UUID,
        variant_ids: list[str],
    ) -> dict[str, int]:
        """Get inventory levels for variants"""
        ...
    
    async def create_draft_order(
        self,
        merchant_id: UUID,
        user_id: UUID,
        line_items: list[dict],
        currency: str,
    ) -> dict:
        """Create a draft order for checkout"""
        ...
    
    async def complete_draft_order(
        self,
        merchant_id: UUID,
        draft_order_id: str,
    ) -> dict:
        """Complete a draft order to create a real order"""
        ...
    
    async def get_order(self, merchant_id: UUID, order_id: str) -> dict:
        """Get order by ID"""
        ...
    
    async def get_customer(
        self,
        merchant_id: UUID,
        customer_id: str,
    ) -> dict:
        """Get customer by ID"""
        ...
    
    async def create_customer(
        self,
        merchant_id: UUID,
        email: str,
        first_name: str | None,
        last_name: str | None,
    ) -> dict:
        """Create a customer record"""
        ...
    
    async def sync_catalog(self, merchant_id: UUID) -> int:
        """Sync catalog from Shopify, return count of products synced"""
        ...
    
    async def is_connected(self, merchant_id: UUID) -> bool:
        """Check if Shopify is connected for this merchant"""
        ...


@runtime_checkable
class RazorpayPort(Protocol):
    """
    Razorpay API client interface
    
    This protocol defines all operations the SDK needs from Razorpay.
    Implementations can be:
    - RealRazorpayClient: Uses Razorpay REST API with test/live keys
    - MockRazorpayClient: For testing without credentials (raises on payment)
    """
    
    async def create_order(
        self,
        merchant_id: UUID,
        amount: Decimal,
        currency: str,
        receipt_id: str,
        notes: dict | None = None,
    ) -> dict:
        """Create a Razorpay order"""
        ...
    
    async def fetch_order(self, merchant_id: UUID, order_id: str) -> dict:
        """Fetch order details from Razorpay"""
        ...
    
    async def capture_payment(
        self,
        merchant_id: UUID,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> dict:
        """Capture and verify a payment"""
        ...
    
    async def fetch_payment(
        self,
        merchant_id: UUID,
        payment_id: str,
    ) -> dict:
        """Fetch payment details"""
        ...
    
    async def refund_payment(
        self,
        merchant_id: UUID,
        payment_id: str,
        amount: Decimal,
        notes: dict | None = None,
    ) -> dict:
        """Refund a payment"""
        ...
    
    async def verify_webhook_signature(
        self,
        merchant_id: UUID,
        payload: bytes,
        signature: str,
    ) -> bool:
        """Verify Razorpay webhook signature"""
        ...
    
    async def is_connected(self, merchant_id: UUID) -> bool:
        """Check if Razorpay is connected for this merchant"""
        ...
