"""
Core types for Agent Commerce SDK

All types are Pydantic models for validation and serialization.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID


class PolicyDecisionStatus(str, Enum):
    """Policy evaluation result"""
    ALLOW = "ALLOW"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    DENY = "DENY"


class ApprovalStatus(str, Enum):
    """Approval request status"""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class OrderStatus(str, Enum):
    """Order lifecycle status"""
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    PROCESSING = "PROCESSING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class PaymentStatus(str, Enum):
    """Payment status"""
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class AuditEventType(str, Enum):
    """Audit event types"""
    USER_CREATED = "USER_CREATED"
    AGENT_CREATED = "AGENT_CREATED"
    MERCHANT_CREATED = "MERCHANT_CREATED"
    POLICY_CREATED = "POLICY_CREATED"
    POLICY_UPDATED = "POLICY_UPDATED"
    CART_CREATED = "CART_CREATED"
    CART_UPDATED = "CART_UPDATED"
    CHECKOUT_CREATED = "CHECKOUT_CREATED"
    CHECKOUT_REFRESHED = "CHECKOUT_REFRESHED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_DECIDED = "APPROVAL_DECIDED"
    PAYMENT_INITIATED = "PAYMENT_INITIATED"
    PAYMENT_COMPLETED = "PAYMENT_COMPLETED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_UPDATED = "ORDER_UPDATED"
    WEBHOOK_RECEIVED = "WEBHOOK_RECEIVED"
    TOOL_CALLED = "TOOL_CALLED"
    POLICY_EVALUATED = "POLICY_EVALUATED"


@dataclass
class User:
    """User account - either admin or customer"""
    user_id: UUID
    email: str
    role: str  # "admin" or "customer"
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Agent:
    """AI agent with delegated authority"""
    agent_id: UUID
    name: str
    kind: str  # "shopper" or "merchant_companion"
    merchant_id: UUID
    model: str
    system_prompt: str
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Merchant:
    """Merchant account"""
    merchant_id: UUID
    user_id: UUID  # owning admin
    name: str
    currency: str
    shopify_connected: bool
    razorpay_connected: bool
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Product:
    """Product from Shopify catalog"""
    product_id: str
    title: str
    description: str
    vendor: str
    product_type: str
    tags: list[str]
    variants: list["ProductVariant"]
    images: list[str]
    created_at: datetime
    updated_at: datetime


@dataclass
class ProductVariant:
    """Product variant with price and inventory"""
    variant_id: str
    product_id: str
    title: str
    price: Decimal
    compare_at_price: Optional[Decimal]
    sku: str
    inventory_quantity: int
    available: bool
    options: dict[str, str]


@dataclass
class CartLine:
    """Line item in a cart"""
    line_id: str
    variant_id: str
    product_id: str
    title: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Cart:
    """Shopping cart"""
    cart_id: str
    user_id: UUID
    merchant_id: UUID
    lines: list[CartLine]
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal
    currency: str
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Checkout:
    """Checkout session"""
    checkout_id: str
    cart_id: str
    user_id: UUID
    merchant_id: UUID
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal
    currency: str
    fingerprint: str  # hash of commerce facts for approval binding
    next_step: str  # "complete_checkout" or "request_purchase_approval"
    razorpay_order_id: Optional[str]
    shopify_draft_order_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Order:
    """Completed order"""
    order_id: str
    checkout_id: str
    user_id: UUID
    merchant_id: UUID
    status: OrderStatus
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal
    currency: str
    line_items: list[dict[str, Any]]
    shipping_address: Optional[dict[str, Any]]
    billing_address: Optional[dict[str, Any]]
    payment_id: Optional[str]
    shopify_order_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Payment:
    """Payment record"""
    payment_id: str
    order_id: str
    checkout_id: str
    amount: Decimal
    currency: str
    status: PaymentStatus
    razorpay_payment_id: Optional[str]
    razorpay_signature: Optional[str]
    captured_at: Optional[datetime]
    failed_reason: Optional[str]
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Approval:
    """Purchase approval request"""
    approval_id: str
    checkout_id: str
    user_id: UUID
    merchant_id: UUID
    amount: Decimal
    currency: str
    fingerprint: str
    status: ApprovalStatus
    decided_by: Optional[UUID]
    decided_at: Optional[datetime]
    reason: Optional[str]
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyRule:
    """Single policy rule"""
    rule_id: str
    scope: str  # "all", "category", "vendor", "product"
    scope_value: Optional[str]
    max_transaction_amount: Optional[Decimal]
    daily_limit: Optional[Decimal]
    approval_threshold: Optional[Decimal]
    requires_approval: bool
    priority: int


@dataclass
class Policy:
    """Spending policy"""
    policy_id: str
    merchant_id: UUID
    user_id: Optional[UUID]  # None = default policy for all users
    version: int
    rules: list[PolicyRule]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyDecision:
    """Result of policy evaluation"""
    decision: PolicyDecisionStatus
    rule_matched: Optional[PolicyRule]
    reason: str
    requires_approval: bool
    approval_amount: Optional[Decimal]


@dataclass
class AuditEvent:
    """Append-only audit log entry"""
    event_id: str
    event_type: AuditEventType
    timestamp: datetime
    actor_type: str  # "user", "agent", "system"
    actor_id: Optional[UUID]
    resource_type: str
    resource_id: str
    action: str
    old_state: Optional[dict[str, Any]]
    new_state: Optional[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionRecord:
    """Evidence-backed decision record for audit"""
    record_id: str
    decision_type: str  # "policy_evaluation", "approval_decision", "payment_authorization"
    timestamp: datetime
    actor_type: str
    actor_id: Optional[UUID]
    input_facts: dict[str, Any]
    decision: str
    evidence: list[str]  # references to supporting evidence
    reasoning: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    """Authenticated session"""
    session_id: str
    user_id: UUID
    merchant_id: UUID
    agent_id: Optional[UUID]
    scopes: list[str]
    created_at: datetime
    expires_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RequestContext:
    """Request context with identity and authorization"""
    user_id: UUID
    merchant_id: UUID
    agent_id: Optional[UUID]
    session_id: str
    scopes: list[str]
    idempotency_key: Optional[str]
