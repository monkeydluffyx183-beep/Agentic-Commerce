"""
Agent Commerce SDK Client

This is the main facade for using the SDK programmatically.
All operations route through mcp.tools.execute_tool for consistency.
"""

import asyncio
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from .core.types import (
    Cart,
    Checkout,
    Order,
    Payment,
    Product,
    Approval,
    Policy,
    RequestContext,
)
from .core.errors import ConfigurationError, PaymentError


class AgentCommerce:
    """
    Main SDK facade for agent commerce operations
    
    Example:
        commerce = AgentCommerce(session=session, shopify=shopify, razorpay=razorpay, ctx=ctx)
        
        products = await commerce.catalog.search(query="hoodie", max_price=Decimal("2000"))
        cart = await commerce.cart.create(lines=[{"variant_id": "...", "quantity": 1}])
        checkout = await commerce.checkout.create(cart_id=cart["cart_id"])
        
        if checkout["next_step"] == "request_purchase_approval":
            await commerce.checkout.request_approval(checkout["checkout_id"])
            # ... user approves via dashboard ...
        
        payment = await commerce.checkout.complete(checkout["checkout_id"])
    """
    
    def __init__(
        self,
        session: dict[str, Any],
        shopify: Any,  # ShopifyPort implementation
        razorpay: Any,  # RazorpayPort implementation
        ctx: RequestContext,
    ):
        self.session = session
        self.shopify = shopify
        self.razorpay = razorpay
        self.ctx = ctx
        
        # Sub-modules
        self.catalog = CatalogOperations(self)
        self.cart = CartOperations(self)
        self.checkout = CheckoutOperations(self)
        self.orders = OrderOperations(self)
        self.payments = PaymentOperations(self)
        self.approvals = ApprovalOperations(self)
        self.policy = PolicyOperations(self)
    
    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """
        Execute a tool through the unified dispatcher
        
        This routes through mcp.tools.execute_tool ensuring consistent
        validation, authorization, and audit logging.
        """
        # Import here to avoid circular dependency
        from ..mcp.tools import execute_tool
        
        return await execute_tool(
            tool_name=tool_name,
            arguments=arguments,
            ctx=self.ctx,
            shopify=self.shopify,
            razorpay=self.razorpay,
        )


class CatalogOperations:
    """Catalog read operations"""
    
    def __init__(self, commerce: AgentCommerce):
        self.commerce = commerce
    
    async def search(
        self,
        query: str | None = None,
        max_price: Decimal | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Search products in catalog"""
        return await self.commerce.execute_tool(
            "search_catalog",
            {"query": query, "max_price": str(max_price) if max_price else None, "limit": limit},
        )
    
    async def get_product(self, product_id: str) -> dict:
        """Get product details"""
        return await self.commerce.execute_tool(
            "get_product",
            {"product_id": product_id},
        )
    
    async def get_inventory(self, variant_ids: list[str]) -> dict[str, int]:
        """Get inventory levels for variants"""
        return await self.commerce.execute_tool(
            "get_inventory",
            {"variant_ids": variant_ids},
        )


class CartOperations:
    """Cart management operations"""
    
    def __init__(self, commerce: AgentCommerce):
        self.commerce = commerce
    
    async def create(self, lines: list[dict]) -> dict:
        """Create a new cart"""
        return await self.commerce.execute_tool(
            "create_cart",
            {"lines": lines},
        )
    
    async def add_item(self, cart_id: str, variant_id: str, quantity: int = 1) -> dict:
        """Add item to cart"""
        return await self.commerce.execute_tool(
            "add_to_cart",
            {"cart_id": cart_id, "variant_id": variant_id, "quantity": quantity},
        )
    
    async def remove_item(self, cart_id: str, line_id: str) -> dict:
        """Remove item from cart"""
        return await self.commerce.execute_tool(
            "remove_from_cart",
            {"cart_id": cart_id, "line_id": line_id},
        )
    
    async def update(self, cart_id: str, lines: list[dict]) -> dict:
        """Update cart lines"""
        return await self.commerce.execute_tool(
            "update_cart",
            {"cart_id": cart_id, "lines": lines},
        )
    
    async def get(self, cart_id: str) -> dict:
        """Get cart details"""
        return await self.commerce.execute_tool(
            "get_cart",
            {"cart_id": cart_id},
        )


class CheckoutOperations:
    """Checkout and payment operations"""
    
    def __init__(self, commerce: AgentCommerce):
        self.commerce = commerce
    
    async def create(self, cart_id: str) -> dict:
        """Create checkout from cart"""
        return await self.commerce.execute_tool(
            "create_checkout",
            {"cart_id": cart_id},
        )
    
    async def refresh(self, checkout_id: str) -> dict:
        """Refresh checkout (e.g., after price changes)"""
        return await self.commerce.execute_tool(
            "refresh_checkout",
            {"checkout_id": checkout_id},
        )
    
    async def request_approval(self, checkout_id: str) -> dict:
        """Request purchase approval"""
        return await self.commerce.execute_tool(
            "request_purchase_approval",
            {"checkout_id": checkout_id},
        )
    
    async def complete(
        self,
        checkout_id: str,
        razorpay_payment_id: str | None = None,
        razorpay_signature: str | None = None,
    ) -> dict:
        """Complete checkout with payment"""
        args = {"checkout_id": checkout_id}
        if razorpay_payment_id:
            args["razorpay_payment_id"] = razorpay_payment_id
        if razorpay_signature:
            args["razorpay_signature"] = razorpay_signature
        return await self.commerce.execute_tool(
            "complete_checkout",
            args,
        )
    
    async def get(self, checkout_id: str) -> dict:
        """Get checkout details"""
        return await self.commerce.execute_tool(
            "get_checkout",
            {"checkout_id": checkout_id},
        )


class OrderOperations:
    """Order read operations"""
    
    def __init__(self, commerce: AgentCommerce):
        self.commerce = commerce
    
    async def get(self, order_id: str) -> dict:
        """Get order details"""
        return await self.commerce.execute_tool(
            "get_order",
            {"order_id": order_id},
        )
    
    async def get_history(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        """Get user's order history"""
        return await self.commerce.execute_tool(
            "get_order_history",
            {"limit": limit, "offset": offset},
        )


class PaymentOperations:
    """Payment status operations"""
    
    def __init__(self, commerce: AgentCommerce):
        self.commerce = commerce
    
    async def get_status(self, payment_id: str) -> dict:
        """Get payment status"""
        return await self.commerce.execute_tool(
            "get_payment_status",
            {"payment_id": payment_id},
        )


class ApprovalOperations:
    """Approval management operations"""
    
    def __init__(self, commerce: AgentCommerce):
        self.commerce = commerce
    
    async def list_pending(self) -> list[dict]:
        """List pending approvals for user"""
        return await self.commerce.execute_tool(
            "list_approvals",
            {"status": "PENDING"},
        )
    
    async def get(self, approval_id: str) -> dict:
        """Get approval details"""
        return await self.commerce.execute_tool(
            "get_approval",
            {"approval_id": approval_id},
        )
    
    async def decide(
        self,
        approval_id: str,
        approved: bool,
        reason: str | None = None,
    ) -> dict:
        """Decide on an approval (requires approval:decide scope)"""
        return await self.commerce.execute_tool(
            "decide_approval",
            {
                "approval_id": approval_id,
                "approved": approved,
                "reason": reason,
            },
        )


class PolicyOperations:
    """Policy read operations"""
    
    def __init__(self, commerce: AgentCommerce):
        self.commerce = commerce
    
    async def get(self) -> dict:
        """Get active policy for user"""
        return await self.commerce.execute_tool(
            "get_policy",
            {},
        )
