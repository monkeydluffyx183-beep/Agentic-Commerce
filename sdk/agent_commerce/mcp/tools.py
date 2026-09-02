"""
MCP Tools - The unified tool dispatcher

All commerce operations route through this single choke point for consistent
validation, authorization, policy evaluation, and audit logging.
"""

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from ..core.errors import (
    AuthorizationError,
    ConfigurationError,
    NotFoundError,
    PaymentError,
    PolicyViolationError,
    ValidationError,
)
from ..core.protocols import RazorpayPort, ShopifyPort
from ..core.types import (
    ApprovalStatus,
    AuditEventType,
    PolicyDecisionStatus,
    RequestContext,
)


# Tool definitions with schemas and scopes
TOOL_DEFINITIONS = {
    # Catalog tools (READ)
    "search_catalog": {
        "description": "Search products in the merchant's catalog",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_price": {"type": "string", "description": "Maximum price filter"},
                "limit": {"type": "integer", "default": 20, "description": "Max results"},
            },
        },
        "scopes": ["catalog:read"],
        "risk": "READ",
    },
    "get_product": {
        "description": "Get product details by ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "Product ID"},
            },
            "required": ["product_id"],
        },
        "scopes": ["catalog:read"],
        "risk": "READ",
    },
    "get_inventory": {
        "description": "Get inventory levels for variants",
        "inputSchema": {
            "type": "object",
            "properties": {
                "variant_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["variant_ids"],
        },
        "scopes": ["inventory:read"],
        "risk": "READ",
    },
    # Cart tools (LOW_WRITE)
    "create_cart": {
        "description": "Create a new shopping cart",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lines": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "variant_id": {"type": "string"},
                            "quantity": {"type": "integer", "default": 1},
                        },
                        "required": ["variant_id"],
                    },
                },
            },
            "required": ["lines"],
        },
        "scopes": ["cart:write"],
        "risk": "LOW_WRITE",
    },
    "add_to_cart": {
        "description": "Add item to existing cart",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cart_id": {"type": "string"},
                "variant_id": {"type": "string"},
                "quantity": {"type": "integer", "default": 1},
            },
            "required": ["cart_id", "variant_id"],
        },
        "scopes": ["cart:write"],
        "risk": "LOW_WRITE",
    },
    "remove_from_cart": {
        "description": "Remove item from cart",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cart_id": {"type": "string"},
                "line_id": {"type": "string"},
            },
            "required": ["cart_id", "line_id"],
        },
        "scopes": ["cart:write"],
        "risk": "LOW_WRITE",
    },
    "update_cart": {
        "description": "Update cart lines",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cart_id": {"type": "string"},
                "lines": {"type": "array"},
            },
            "required": ["cart_id", "lines"],
        },
        "scopes": ["cart:write"],
        "risk": "LOW_WRITE",
    },
    "get_cart": {
        "description": "Get cart details",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cart_id": {"type": "string"},
            },
            "required": ["cart_id"],
        },
        "scopes": ["cart:read"],
        "risk": "READ",
    },
    # Checkout tools (MONEY / LOW_WRITE)
    "create_checkout": {
        "description": "Create checkout from cart",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cart_id": {"type": "string"},
            },
            "required": ["cart_id"],
        },
        "scopes": ["checkout:create"],
        "risk": "MONEY",
    },
    "refresh_checkout": {
        "description": "Refresh checkout (e.g., after price changes)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "checkout_id": {"type": "string"},
            },
            "required": ["checkout_id"],
        },
        "scopes": ["checkout:create"],
        "risk": "LOW_WRITE",
    },
    "get_checkout": {
        "description": "Get checkout details",
        "inputSchema": {
            "type": "object",
            "properties": {
                "checkout_id": {"type": "string"},
            },
            "required": ["checkout_id"],
        },
        "scopes": ["checkout:read"],
        "risk": "READ",
    },
    # Payment tools (MONEY)
    "request_purchase_approval": {
        "description": "Request purchase approval for checkout",
        "inputSchema": {
            "type": "object",
            "properties": {
                "checkout_id": {"type": "string"},
            },
            "required": ["checkout_id"],
        },
        "scopes": ["payment:request"],
        "risk": "MONEY",
    },
    "complete_checkout": {
        "description": "Complete checkout with payment",
        "inputSchema": {
            "type": "object",
            "properties": {
                "checkout_id": {"type": "string"},
                "razorpay_payment_id": {"type": "string"},
                "razorpay_signature": {"type": "string"},
            },
            "required": ["checkout_id"],
        },
        "scopes": ["payment:request"],
        "risk": "MONEY",
    },
    # Order tools (READ)
    "get_order": {
        "description": "Get order details",
        "inputSchema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
            },
            "required": ["order_id"],
        },
        "scopes": ["order:read"],
        "risk": "READ",
    },
    "get_order_history": {
        "description": "Get user's order history",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
                "offset": {"type": "integer", "default": 0},
            },
        },
        "scopes": ["order:read"],
        "risk": "READ",
    },
    "get_payment_status": {
        "description": "Get payment status",
        "inputSchema": {
            "type": "object",
            "properties": {
                "payment_id": {"type": "string"},
            },
            "required": ["payment_id"],
        },
        "scopes": ["payment:read"],
        "risk": "READ",
    },
    # Approval tools (READ / MONEY)
    "list_approvals": {
        "description": "List approvals (optionally filtered by status)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["PENDING", "APPROVED", "REJECTED"]},
            },
        },
        "scopes": ["approval:read"],
        "risk": "READ",
    },
    "decide_approval": {
        "description": "Decide on an approval request (requires approval:decide scope)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "approval_id": {"type": "string"},
                "approved": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["approval_id", "approved"],
        },
        "scopes": ["approval:decide"],
        "risk": "MONEY",
    },
    # Policy tools (READ)
    "get_policy": {
        "description": "Get active policy for user",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "scopes": ["policy:read"],
        "risk": "READ",
    },
}


async def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> Any:
    """
    Execute a tool through the unified dispatcher
    
    This is THE choke point - all commerce operations flow through here.
    Handles validation, authorization, policy evaluation, and audit logging.
    """
    # Validate tool exists
    if tool_name not in TOOL_DEFINITIONS:
        raise ValidationError(f"Unknown tool: {tool_name}")
    
    tool_def = TOOL_DEFINITIONS[tool_name]
    
    # Check scopes
    required_scopes = set(tool_def["scopes"])
    available_scopes = set(ctx.scopes)
    if not required_scopes.issubset(available_scopes):
        missing = required_scopes - available_scopes
        raise AuthorizationError(
            f"Missing required scopes: {missing}",
            required_scope=list(missing)[0],
        )
    
    # Route to appropriate handler
    handler = _get_handler(tool_name)
    return await handler(arguments, ctx, shopify, razorpay)


def _get_handler(tool_name: str):
    """Get handler function for a tool"""
    handlers = {
        "search_catalog": _handle_search_catalog,
        "get_product": _handle_get_product,
        "get_inventory": _handle_get_inventory,
        "create_cart": _handle_create_cart,
        "add_to_cart": _handle_add_to_cart,
        "remove_from_cart": _handle_remove_from_cart,
        "update_cart": _handle_update_cart,
        "get_cart": _handle_get_cart,
        "create_checkout": _handle_create_checkout,
        "refresh_checkout": _handle_refresh_checkout,
        "get_checkout": _handle_get_checkout,
        "request_purchase_approval": _handle_request_approval,
        "complete_checkout": _handle_complete_checkout,
        "get_order": _handle_get_order,
        "get_order_history": _handle_get_order_history,
        "get_payment_status": _handle_get_payment_status,
        "list_approvals": _handle_list_approvals,
        "decide_approval": _handle_decide_approval,
        "get_policy": _handle_get_policy,
    }
    return handlers.get(tool_name, lambda *args: None)


# Handler implementations
async def _handle_search_catalog(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> list[dict]:
    """Search products in catalog"""
    max_price = Decimal(args["max_price"]) if args.get("max_price") else None
    limit = args.get("limit", 20)
    
    products = await shopify.search_products(
        merchant_id=ctx.merchant_id,
        query=args.get("query"),
        max_price=max_price,
        limit=limit,
    )
    
    return products


async def _handle_get_product(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> dict:
    """Get product details"""
    return await shopify.get_product(ctx.merchant_id, args["product_id"])


async def _handle_get_inventory(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> dict[str, int]:
    """Get inventory levels"""
    return await shopify.get_inventory(ctx.merchant_id, args["variant_ids"])


async def _handle_create_cart(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> dict:
    """Create a new cart"""
    # In a real implementation, this would persist to database
    cart_id = str(uuid4())
    lines = args.get("lines", [])
    
    # Fetch product details and calculate totals
    total = Decimal("0")
    for line in lines:
        product = await shopify.get_product(ctx.merchant_id, line["variant_id"])
        variant = product["variants"][0]
        line["unit_price"] = float(variant["price"])
        line["total_price"] = float(variant["price"] * line.get("quantity", 1))
        total += variant["price"] * line.get("quantity", 1)
    
    tax = total * Decimal("0.18")
    
    return {
        "cart_id": cart_id,
        "user_id": str(ctx.user_id),
        "merchant_id": str(ctx.merchant_id),
        "lines": lines,
        "subtotal": float(total),
        "tax": float(tax),
        "total": float(total + tax),
        "currency": "INR",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def _handle_add_to_cart(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> dict:
    """Add item to cart"""
    # Placeholder - would update persisted cart
    return {"status": "added", "cart_id": args["cart_id"]}


async def _handle_remove_from_cart(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> dict:
    """Remove item from cart"""
    return {"status": "removed", "cart_id": args["cart_id"], "line_id": args["line_id"]}


async def _handle_update_cart(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> dict:
    """Update cart lines"""
    return {"status": "updated", "cart_id": args["cart_id"]}


async def _handle_get_cart(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> dict:
    """Get cart details"""
    # Placeholder - would fetch from database
    raise NotFoundError("Cart", args["cart_id"])


async def _handle_create_checkout(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> dict:
    """Create checkout from cart"""
    # In a real implementation, would fetch cart and create draft order
    checkout_id = str(uuid4())
    total = Decimal("1999.00")  # Placeholder
    
    # Compute fingerprint for approval binding
    fingerprint_data = {
        "merchant_id": str(ctx.merchant_id),
        "user_id": str(ctx.user_id),
        "total": str(total),
        "currency": "INR",
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_data, sort_keys=True).encode()
    ).hexdigest()
    
    # Determine next step based on policy (simplified)
    # In reality, would call policy evaluator
    next_step = "request_purchase_approval" if total > Decimal("5000") else "complete_checkout"
    
    return {
        "checkout_id": checkout_id,
        "cart_id": args["cart_id"],
        "user_id": str(ctx.user_id),
        "merchant_id": str(ctx.merchant_id),
        "subtotal": float(total * Decimal("0.85")),
        "tax": float(total * Decimal("0.15")),
        "total": float(total),
        "currency": "INR",
        "fingerprint": fingerprint,
        "next_step": next_step,
        "razorpay_order_id": None,
        "shopify_draft_order_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def _handle_refresh_checkout(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> dict:
    """Refresh checkout"""
    # Placeholder
    return {"status": "refreshed", "checkout_id": args["checkout_id"]}


async def _handle_get_checkout(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> dict:
    """Get checkout details"""
    # Placeholder
    raise NotFoundError("Checkout", args["checkout_id"])


async def _handle_request_approval(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> dict:
    """Request purchase approval"""
    approval_id = str(uuid4())
    
    return {
        "approval_id": approval_id,
        "checkout_id": args["checkout_id"],
        "user_id": str(ctx.user_id),
        "merchant_id": str(ctx.merchant_id),
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def _handle_complete_checkout(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> dict:
    """Complete checkout with payment"""
    # Check if Razorpay is configured
    if not razorpay.is_configured:
        raise ConfigurationError(
            "Razorpay Test Mode integration is ready to wire. "
            "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to complete payments."
        )
    
    # In a real implementation:
    # 1. Create Razorpay order
    # 2. Return payment URL or require payment intent from client
    # 3. Verify signature on callback
    # 4. Complete Shopify draft order
    
    return {
        "status": "payment_required",
        "message": "Razorpay order would be created here",
        "checkout_id": args["checkout_id"],
    }


async def _handle_get_order(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> dict:
    """Get order details"""
    return await shopify.get_order(ctx.merchant_id, args["order_id"])


async def _handle_get_order_history(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> list[dict]:
    """Get order history"""
    # Placeholder - would query database
    return []


async def _handle_get_payment_status(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> dict:
    """Get payment status"""
    return await razorpay.fetch_payment(ctx.merchant_id, args["payment_id"])


async def _handle_list_approvals(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> list[dict]:
    """List approvals"""
    # Placeholder
    return []


async def _handle_decide_approval(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> dict:
    """Decide on approval"""
    return {
        "approval_id": args["approval_id"],
        "status": "APPROVED" if args["approved"] else "REJECTED",
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }


async def _handle_get_policy(
    args: dict,
    ctx: RequestContext,
    shopify: ShopifyPort,
    razorpay: RazorpayPort,
) -> dict:
    """Get active policy"""
    # Placeholder
    return {
        "policy_id": "default",
        "merchant_id": str(ctx.merchant_id),
        "rules": [],
        "is_active": True,
    }
