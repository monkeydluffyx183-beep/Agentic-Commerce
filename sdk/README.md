# Agent Commerce SDK

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

Agent Commerce SDK enables AI agents to shop and transact on behalf of users under explicit authorization and policy. This is a **control plane**, not another storefront, chatbot, or payment gateway.

- **Shopify** remains the system of record for commerce
- **Razorpay** remains the system of record for payments  
- **This SDK** owns orchestration, identity, delegated authorization, deterministic policy, approval, reconciliation, and audit

## Installation

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ./sdk
```

## Quick Start

```python
from agent_commerce import AgentCommerce

commerce = AgentCommerce(session=session, shopify=shopify, razorpay=razorpay, ctx=ctx)

# Search catalog
products = await commerce.catalog.search(query="hoodie", max_price=Decimal("2000"))

# Create cart
cart = await commerce.cart.create(lines=[{"variant_id": "...", "quantity": 1}])

# Create checkout
checkout = await commerce.checkout.create(cart_id=cart["cart_id"])

# Request approval if needed
if checkout["next_step"] == "request_purchase_approval":
    await commerce.checkout.request_approval(checkout["checkout_id"])
    # ... user approves via the dashboard ...

# Complete payment
payment = await commerce.checkout.complete(checkout["checkout_id"])
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full design details.

```
AI AGENT (Local, or any external MCP client)
        |
        v
UNIFIED MCP SERVER  (/mcp -- official `mcp` SDK, streamable-HTTP)
        |
        v
mcp.tools.execute_tool  <-- the single dispatch choke point
        |
        v
AGENT COMMERCE SDK (sdk/agent_commerce/)
  commerce/  identity/  policy/  audit/  security/
        |                    |
        v                    v
  shopify/ (ShopifyPort)   razorpay/ (RazorpayPort)
        |                    |
        v                    v
  Shopify commerce state   Razorpay payment state
```

## Security Model

- **LLM never authorizes payment**: Qwen2.5:7B selects tools and explains results; it never computes prices, evaluates policy, or resolves identity
- **Deterministic policy engine**: Pure, rule-based logic with no LLM involvement
- **Checkout fingerprinting**: Every approval is bound to exact commerce facts
- **Ownership enforcement**: Every resource load checks ownership
- **Explicit tool allowlist**: Strict Pydantic schema per tool
- **Idempotency**: Deduplicated webhook processing, payment execution, and approval creation
- **Signed webhooks only**: HMAC-SHA256 verification for Shopify and Razorpay webhooks

## MCP Tools

The unified MCP server exposes these tools:

| Tool | Risk | Scope |
|------|------|-------|
| search_catalog, get_product, get_inventory | READ | catalog:read / inventory:read |
| create_cart, add_to_cart, remove_from_cart | LOW_WRITE | cart:write |
| create_checkout, refresh_checkout | MONEY / LOW_WRITE | checkout:create |
| request_purchase_approval | MONEY | payment:request |
| complete_checkout | MONEY | payment:request |
| decide_approval | MONEY | approval:decide (opt-in) |

## Testing

```bash
pytest tests/unit tests/security          # fast, no external dependencies
pytest tests/mcp                          # MCP protocol conformance
pytest tests/razorpay                     # real Razorpay test-mode API
pytest tests/shopify                      # real Shopify Admin API
pytest tests/ai tests/e2e                 # real Ollama inference
```

## License

MIT
