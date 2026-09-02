"""
Shopify Admin API GraphQL client

Uses the GraphQL Admin API exclusively - never storefront HTML scraping.
Checkout is built on Shopify Draft Orders since payment capture happens
through Razorpay rather than Shopify's native checkout.
"""

import hashlib
import os
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

import httpx

from ..core.errors import ConfigurationError, ShopifyError
from ..core.protocols import ShopifyPort
from .tokens import TokenManager


class ShopifyClient:
    """
    Real Shopify Admin API GraphQL client
    
    Requires:
    - SHOPIFY_SHOP_DOMAIN (e.g., your-store.myshopify.com)
    - SHOPIFY_CLIENT_ID
    - SHOPIFY_CLIENT_SECRET
    - Optional: SHOPIFY_ACCESS_TOKEN (pinned token, takes precedence)
    """
    
    GRAPHQL_ENDPOINT = "/admin/api/2024-01/graphql.json"
    
    def __init__(self, shop_domain: str | None = None, client_id: str | None = None, 
                 client_secret: str | None = None, pinned_token: str | None = None):
        self.shop_domain = shop_domain or os.getenv("SHOPIFY_SHOP_DOMAIN")
        self.client_id = client_id or os.getenv("SHOPIFY_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("SHOPIFY_CLIENT_SECRET")
        self.pinned_token = pinned_token or os.getenv("SHOPIFY_ACCESS_TOKEN")
        
        self._token_manager: Optional[TokenManager] = None
        
        if self.shop_domain and (self.client_id and self.client_secret):
            self._token_manager = TokenManager(
                shop_domain=self.shop_domain,
                client_id=self.client_id,
                client_secret=self.client_secret,
                pinned_token=self.pinned_token,
            )
    
    @property
    def is_configured(self) -> bool:
        """Check if Shopify credentials are configured"""
        return self._token_manager is not None
    
    async def _get_graphql_client(self) -> httpx.AsyncClient:
        """Get authenticated HTTP client for GraphQL requests"""
        if not self._token_manager:
            raise ConfigurationError(
                "Shopify not configured. Set SHOPIFY_SHOP_DOMAIN, SHOPIFY_CLIENT_ID, "
                "and SHOPIFY_CLIENT_SECRET in environment.",
                missing_var="SHOPIFY_*",
            )
        
        token = await self._token_manager.get_token()
        base_url = f"https://{self.shop_domain}"
        
        return httpx.AsyncClient(
            base_url=base_url,
            headers={
                "X-Shopify-Access-Token": token,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
    
    async def _execute_graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> dict:
        """Execute GraphQL query with automatic 401 retry"""
        client = await self._get_graphql_client()
        
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name
        
        try:
            response = await client.post(self.GRAPHQL_ENDPOINT, json=payload)
            
            # Auto-retry on 401 (token expired)
            if response.status_code == 401 and not self.pinned_token:
                await self._token_manager.invalidate()
                client = await self._get_graphql_client()
                response = await client.post(self.GRAPHQL_ENDPOINT, json=payload)
            
            response.raise_for_status()
            data = response.json()
            
            if "errors" in data:
                raise ShopifyError(
                    f"GraphQL errors: {data['errors']}",
                    graphql_errors=data["errors"],
                )
            
            return data.get("data", {})
        except httpx.HTTPStatusError as e:
            raise ShopifyError(
                f"Shopify API error: {e}",
                status_code=e.response.status_code,
            )
        finally:
            await client.aclose()
    
    async def search_products(
        self,
        merchant_id: UUID,
        query: str | None = None,
        max_price: Decimal | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Search products in catalog"""
        filter_parts = []
        if query:
            filter_parts.append(f'"{query}"')
        if max_price:
            filter_parts.append(f'variants.price:<={max_price}')
        
        filters = " ".join(filter_parts) if filter_parts else "*"
        
        graphql_query = """
        query SearchProducts($query: String!, $first: Int!) {
            products(first: $first, query: $query) {
                edges {
                    node {
                        id
                        title
                        description
                        vendor
                        productType
                        tags
                        createdAt
                        updatedAt
                        images(first: 5) {
                            edges {
                                node {
                                    url
                                }
                            }
                        }
                        variants(first: 10) {
                            edges {
                                node {
                                    id
                                    title
                                    price
                                    compareAtPrice
                                    sku
                                    inventoryQuantity: quantityAvailable
                                    availableForSale
                                    selectedOptions {
                                        name
                                        value
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        
        result = await self._execute_graphql(
            graphql_query,
            variables={"query": filters, "first": limit},
        )
        
        products = []
        for edge in result.get("products", {}).get("edges", []):
            node = edge["node"]
            products.append({
                "product_id": node["id"].replace("gid://shopify/Product/", ""),
                "title": node["title"],
                "description": node["description"] or "",
                "vendor": node["vendor"] or "",
                "product_type": node["productType"] or "",
                "tags": node["tags"].split(", ") if node["tags"] else [],
                "images": [
                    img["node"]["url"]
                    for img in node.get("images", {}).get("edges", [])
                ],
                "variants": [
                    {
                        "variant_id": v["node"]["id"].replace("gid://shopify/ProductVariant/", ""),
                        "product_id": node["id"].replace("gid://shopify/Product/", ""),
                        "title": v["node"]["title"],
                        "price": Decimal(str(v["node"]["price"])),
                        "compare_at_price": (
                            Decimal(str(v["node"]["compareAtPrice"]))
                            if v["node"]["compareAtPrice"] else None
                        ),
                        "sku": v["node"]["sku"] or "",
                        "inventory_quantity": v["node"]["inventoryQuantity"] or 0,
                        "available": v["node"]["availableForSale"],
                        "options": {
                            opt["name"]: opt["value"]
                            for opt in v["node"].get("selectedOptions", [])
                        },
                    }
                    for v in node.get("variants", {}).get("edges", [])
                ],
                "created_at": node["createdAt"],
                "updated_at": node["updatedAt"],
            })
        
        return products
    
    async def get_product(self, merchant_id: UUID, product_id: str) -> dict:
        """Get product by ID"""
        products = await self.search_products(merchant_id, query=f"id:{product_id}", limit=1)
        if not products:
            from ..core.errors import NotFoundError
            raise NotFoundError("Product", product_id)
        return products[0]
    
    async def get_inventory(
        self,
        merchant_id: UUID,
        variant_ids: list[str],
    ) -> dict[str, int]:
        """Get inventory levels for variants"""
        # Build query for specific variant IDs
        ids_query = " OR ".join(f"id:{vid}" for vid in variant_ids)
        
        graphql_query = """
        query GetInventory($query: String!) {
            productVariants(first: 50, query: $query) {
                edges {
                    node {
                        id
                        quantityAvailable
                    }
                }
            }
        }
        """
        
        result = await self._execute_graphql(
            graphql_query,
            variables={"query": ids_query},
        )
        
        inventory = {}
        for edge in result.get("productVariants", {}).get("edges", []):
            node = edge["node"]
            variant_id = node["id"].replace("gid://shopify/ProductVariant/", "")
            inventory[variant_id] = node["quantityAvailable"] or 0
        
        return inventory
    
    async def create_draft_order(
        self,
        merchant_id: UUID,
        user_id: UUID,
        line_items: list[dict],
        currency: str,
    ) -> dict:
        """Create a draft order for checkout"""
        graphql_query = """
        mutation DraftOrderCreate($input: DraftOrderInput!) {
            draftOrderCreate(input: $input) {
                draftOrder {
                    id
                    name
                    lineItems(first: 50) {
                        edges {
                            node {
                                id
                                title
                                quantity
                                originalUnitPrice
                                totalDiscount
                            }
                        }
                    }
                    subtotalPrice
                    totalPrice
                    totalTax
                    currencyCode
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        
        input_items = [
            {
                "variantId": f"gid://shopify/ProductVariant/{item['variant_id']}",
                "quantity": item["quantity"],
            }
            for item in line_items
        ]
        
        result = await self._execute_graphql(
            graphql_query,
            variables={
                "input": {
                    "lineItems": input_items,
                    "currencyCode": currency,
                    "note": f"Agent Commerce checkout for user {user_id}",
                }
            },
        )
        
        draft_order = result.get("draftOrderCreate", {}).get("draftOrder")
        if not draft_order:
            errors = result.get("draftOrderCreate", {}).get("userErrors", [])
            raise ShopifyError(f"Failed to create draft order: {errors}")
        
        return {
            "draft_order_id": draft_order["id"].replace("gid://shopify/DraftOrder/", ""),
            "name": draft_order["name"],
            "subtotal": Decimal(str(draft_order["subtotalPrice"])),
            "total": Decimal(str(draft_order["totalPrice"])),
            "tax": Decimal(str(draft_order["totalTax"])),
            "currency": draft_order["currencyCode"],
            "line_items": [
                {
                    "id": item["node"]["id"],
                    "title": item["node"]["title"],
                    "quantity": item["node"]["quantity"],
                    "unit_price": Decimal(str(item["node"]["originalUnitPrice"])),
                    "discount": Decimal(str(item["node"]["totalDiscount"])),
                }
                for item in draft_order.get("lineItems", {}).get("edges", [])
            ],
        }
    
    async def complete_draft_order(
        self,
        merchant_id: UUID,
        draft_order_id: str,
    ) -> dict:
        """Complete a draft order to create a real order"""
        graphql_query = """
        mutation DraftOrderComplete($id: ID!) {
            draftOrderComplete(id: $id) {
                draftOrder {
                    id
                    status
                    order {
                        id
                        name
                        totalPrice
                        currencyCode
                    }
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        
        result = await self._execute_graphql(
            graphql_query,
            variables={"id": f"gid://shopify/DraftOrder/{draft_order_id}"},
        )
        
        draft_order = result.get("draftOrderComplete", {}).get("draftOrder")
        if not draft_order:
            errors = result.get("draftOrderComplete", {}).get("userErrors", [])
            raise ShopifyError(f"Failed to complete draft order: {errors}")
        
        order = draft_order.get("order")
        return {
            "order_id": order["id"].replace("gid://shopify/Order/", "") if order else None,
            "status": draft_order["status"],
            "total": Decimal(str(order["totalPrice"])) if order else None,
            "currency": order["currencyCode"] if order else None,
        }
    
    async def get_order(self, merchant_id: UUID, order_id: str) -> dict:
        """Get order by ID"""
        graphql_query = """
        query GetOrder($id: ID!) {
            order(id: $id) {
                id
                name
                status
                totalPrice
                currencyCode
                createdAt
                updatedAt
                lineItems(first: 50) {
                    edges {
                        node {
                            title
                            quantity
                            originalUnitPrice
                            totalDiscount
                        }
                    }
                }
                shippingAddress {
                    firstName
                    lastName
                    address1
                    city
                    province
                    zip
                    country
                }
            }
        }
        """
        
        result = await self._execute_graphql(
            graphql_query,
            variables={"id": f"gid://shopify/Order/{order_id}"},
        )
        
        order = result.get("order")
        if not order:
            from ..core.errors import NotFoundError
            raise NotFoundError("Order", order_id)
        
        return {
            "order_id": order["id"].replace("gid://shopify/Order/", ""),
            "name": order["name"],
            "status": order["status"],
            "total": Decimal(str(order["totalPrice"])),
            "currency": order["currencyCode"],
            "created_at": order["createdAt"],
            "updated_at": order["updatedAt"],
            "line_items": [
                {
                    "title": item["node"]["title"],
                    "quantity": item["node"]["quantity"],
                    "unit_price": Decimal(str(item["node"]["originalUnitPrice"])),
                    "discount": Decimal(str(item["node"]["totalDiscount"])),
                }
                for item in order.get("lineItems", {}).get("edges", [])
            ],
            "shipping_address": order.get("shippingAddress"),
        }
    
    async def get_customer(
        self,
        merchant_id: UUID,
        customer_id: str,
    ) -> dict:
        """Get customer by ID"""
        graphql_query = """
        query GetCustomer($id: ID!) {
            customer(id: $id) {
                id
                email
                firstName
                lastName
                createdAt
                updatedAt
                ordersCount
                totalSpent
            }
        }
        """
        
        result = await self._execute_graphql(
            graphql_query,
            variables={"id": f"gid://shopify/Customer/{customer_id}"},
        )
        
        customer = result.get("customer")
        if not customer:
            from ..core.errors import NotFoundError
            raise NotFoundError("Customer", customer_id)
        
        return {
            "customer_id": customer["id"].replace("gid://shopify/Customer/", ""),
            "email": customer["email"],
            "first_name": customer["firstName"],
            "last_name": customer["lastName"],
            "created_at": customer["createdAt"],
            "updated_at": customer["updatedAt"],
            "orders_count": customer["ordersCount"],
            "total_spent": Decimal(str(customer["totalSpent"])) if customer["totalSpent"] else Decimal("0"),
        }
    
    async def create_customer(
        self,
        merchant_id: UUID,
        email: str,
        first_name: str | None,
        last_name: str | None,
    ) -> dict:
        """Create a customer record"""
        graphql_query = """
        mutation CustomerCreate($input: CustomerInput!) {
            customerCreate(input: $input) {
                customer {
                    id
                    email
                    firstName
                    lastName
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        
        input_data = {"email": email}
        if first_name:
            input_data["firstName"] = first_name
        if last_name:
            input_data["lastName"] = last_name
        
        result = await self._execute_graphql(
            graphql_query,
            variables={"input": input_data},
        )
        
        customer = result.get("customerCreate", {}).get("customer")
        if not customer:
            errors = result.get("customerCreate", {}).get("userErrors", [])
            raise ShopifyError(f"Failed to create customer: {errors}")
        
        return {
            "customer_id": customer["id"].replace("gid://shopify/Customer/", ""),
            "email": customer["email"],
            "first_name": customer["firstName"],
            "last_name": customer["lastName"],
        }
    
    async def sync_catalog(self, merchant_id: UUID) -> int:
        """Sync catalog from Shopify, return count of products synced"""
        # This would typically fetch all products and cache them locally
        # For now, we just verify connection works
        products = await self.search_products(merchant_id, query="*", limit=1)
        return len(products)
    
    async def is_connected(self, merchant_id: UUID) -> bool:
        """Check if Shopify is connected for this merchant"""
        if not self.is_configured:
            return False
        try:
            await self.sync_catalog(merchant_id)
            return True
        except Exception:
            return False


# Alias for protocol compliance
ShopifyPort = ShopifyClient
