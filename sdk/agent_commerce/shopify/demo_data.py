"""
Demo Shopify data generator

Provides a dynamically generated (Faker-backed) catalog when real Shopify
credentials are not configured. Satisfies the exact same ShopifyPort interface.
"""

import hashlib
import os
import random
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from ..core.protocols import ShopifyPort


class DemoShopifyClient:
    """
    Demo Shopify client with Faker-generated catalog
    
    Used when SHOPIFY_* credentials are not configured.
    Generates realistic product data on-the-fly.
    """
    
    # Predefined categories for realistic generation
    CATEGORIES = [
        "Apparel", "Electronics", "Home & Garden", "Sports", 
        "Books", "Beauty", "Toys", "Food & Beverage"
    ]
    
    PRODUCT_TEMPLATES = {
        "Apparel": [
            ("Classic Cotton T-Shirt", 299, "Comfortable everyday wear"),
            ("Slim Fit Jeans", 1299, "Modern fit denim"),
            ("Wool Blend Sweater", 2499, "Warm winter essential"),
            ("Black Hoodie", 1899, "Casual streetwear"),
            ("Running Shorts", 799, "Lightweight athletic wear"),
        ],
        "Electronics": [
            ("Wireless Earbuds", 2999, "True wireless with charging case"),
            ("USB-C Hub", 1499, "7-in-1 connectivity"),
            ("Portable Charger", 1999, "10000mAh power bank"),
            ("Smart Watch", 4999, "Fitness tracking and notifications"),
            ("Bluetooth Speaker", 3499, "360-degree sound"),
        ],
        "Home & Garden": [
            ("Ceramic Plant Pot", 599, "Handcrafted planter"),
            ("LED Desk Lamp", 1299, "Adjustable brightness"),
            ("Throw Pillow Set", 999, "Decorative cushions"),
            ("Scented Candle", 499, "Soy wax blend"),
            ("Wall Art Print", 799, "Abstract design"),
        ],
        "Sports": [
            ("Yoga Mat", 899, "Non-slip exercise mat"),
            ("Resistance Bands", 599, "Set of 5 strengths"),
            ("Water Bottle", 399, "Insulated steel"),
            ("Jump Rope", 299, "Speed rope for cardio"),
            ("Foam Roller", 699, "Muscle recovery"),
        ],
    }
    
    VENDOR_NAMES = [
        "Urban Style Co.", "TechGear", "HomeEssentials", "ActiveLife",
        "GreenLeaf", "ModernLiving", "CraftMakers", "FitPro"
    ]
    
    def __init__(self):
        self._generated_products: dict[str, list[dict]] = {}
    
    def _generate_product_id(self, title: str, index: int) -> str:
        """Generate deterministic product ID from title"""
        hash_input = f"{title}_{index}_{os.urandom(8).hex()}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:14]
    
    def _generate_variant_id(self, product_id: str, variant: str) -> str:
        """Generate deterministic variant ID"""
        hash_input = f"{product_id}_{variant}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:14]
    
    def _generate_products(self, merchant_id: UUID) -> list[dict]:
        """Generate demo product catalog"""
        if merchant_id in self._generated_products:
            return self._generated_products[merchant_id]
        
        products = []
        now = datetime.utcnow()
        
        for category, templates in self.PRODUCT_TEMPLATES.items():
            for i, (title, price, description) in enumerate(templates):
                product_id = self._generate_product_id(title, i)
                
                variants = []
                if category == "Apparel":
                    # Multiple sizes/colors
                    sizes = ["S", "M", "L", "XL"]
                    colors = ["Black", "White", "Navy"]
                    for size in sizes:
                        for color in colors:
                            variant_title = f"{size} / {color}"
                            variants.append({
                                "variant_id": self._generate_variant_id(product_id, variant_title),
                                "product_id": product_id,
                                "title": variant_title,
                                "price": Decimal(str(price)),
                                "compare_at_price": Decimal(str(int(price * 1.2))) if random.random() > 0.7 else None,
                                "sku": f"{product_id.upper()}-{size}-{color.upper()[:3]}",
                                "inventory_quantity": random.randint(10, 100),
                                "available": True,
                                "options": {"Size": size, "Color": color},
                            })
                else:
                    # Single variant
                    variants.append({
                        "variant_id": self._generate_variant_id(product_id, "default"),
                        "product_id": product_id,
                        "title": "Default",
                        "price": Decimal(str(price)),
                        "compare_at_price": None,
                        "sku": f"{product_id.upper()}-DEFAULT",
                        "inventory_quantity": random.randint(20, 200),
                        "available": True,
                        "options": {},
                    })
                
                products.append({
                    "product_id": product_id,
                    "title": title,
                    "description": description,
                    "vendor": random.choice(self.VENDOR_NAMES),
                    "product_type": category,
                    "tags": [category.lower(), "demo", f"under-{(price // 500 + 1) * 500}"],
                    "images": [
                        f"https://picsum.photos/seed/{product_id}/400/400.jpg"
                    ],
                    "variants": variants,
                    "created_at": (now - timedelta(days=random.randint(1, 365))).isoformat(),
                    "updated_at": now.isoformat(),
                })
        
        self._generated_products[merchant_id] = products
        return products
    
    async def search_products(
        self,
        merchant_id: UUID,
        query: str | None = None,
        max_price: Decimal | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Search products in demo catalog"""
        products = self._generate_products(merchant_id)
        
        results = []
        for product in products:
            # Filter by query
            if query and query != "*":
                query_lower = query.lower().strip('"')
                searchable = f"{product['title']} {product['description']} {product['product_type']} {' '.join(product['tags'])}".lower()
                if query_lower not in searchable:
                    continue
            
            # Filter by max price (check cheapest variant)
            if max_price:
                min_price = min(v["price"] for v in product["variants"])
                if min_price > max_price:
                    continue
            
            results.append(product)
            
            if len(results) >= limit:
                break
        
        return results
    
    async def get_product(self, merchant_id: UUID, product_id: str) -> dict:
        """Get product by ID"""
        products = self._generate_products(merchant_id)
        for product in products:
            if product["product_id"] == product_id:
                return product
        
        from ..core.errors import NotFoundError
        raise NotFoundError("Product", product_id)
    
    async def get_inventory(
        self,
        merchant_id: UUID,
        variant_ids: list[str],
    ) -> dict[str, int]:
        """Get inventory levels for variants"""
        products = self._generate_products(merchant_id)
        inventory = {}
        
        for product in products:
            for variant in product["variants"]:
                if variant["variant_id"] in variant_ids:
                    inventory[variant["variant_id"]] = variant["inventory_quantity"]
        
        return inventory
    
    async def create_draft_order(
        self,
        merchant_id: UUID,
        user_id: UUID,
        line_items: list[dict],
        currency: str,
    ) -> dict:
        """Create a draft order for checkout (demo mode)"""
        products = self._generate_products(merchant_id)
        
        # Find variants and build order
        order_items = []
        subtotal = Decimal("0")
        
        for item in line_items:
            for product in products:
                for variant in product["variants"]:
                    if variant["variant_id"] == item["variant_id"]:
                        quantity = item.get("quantity", 1)
                        total = variant["price"] * quantity
                        order_items.append({
                            "variant_id": variant["variant_id"],
                            "product_id": variant["product_id"],
                            "title": f"{product['title']} - {variant['title']}",
                            "quantity": quantity,
                            "unit_price": variant["price"],
                            "total_price": total,
                        })
                        subtotal += total
                        break
        
        tax = subtotal * Decimal("0.18")  # 18% GST
        total = subtotal + tax
        
        return {
            "draft_order_id": f"draft_{hashlib.md5(os.urandom(16)).hexdigest()[:12]}",
            "name": f"#DEMO-{random.randint(1000, 9999)}",
            "subtotal": subtotal,
            "total": total,
            "tax": tax,
            "currency": currency,
            "line_items": order_items,
        }
    
    async def complete_draft_order(
        self,
        merchant_id: UUID,
        draft_order_id: str,
    ) -> dict:
        """Complete a draft order to create a real order (demo mode)"""
        return {
            "order_id": f"order_{hashlib.md5(os.urandom(16)).hexdigest()[:12]}",
            "status": "confirmed",
            "total": None,  # Will be set from checkout
            "currency": "INR",
        }
    
    async def get_order(self, merchant_id: UUID, order_id: str) -> dict:
        """Get order by ID (demo mode)"""
        from ..core.errors import NotFoundError
        raise NotFoundError("Order", order_id)
    
    async def get_customer(
        self,
        merchant_id: UUID,
        customer_id: str,
    ) -> dict:
        """Get customer by ID (demo mode)"""
        from ..core.errors import NotFoundError
        raise NotFoundError("Customer", customer_id)
    
    async def create_customer(
        self,
        merchant_id: UUID,
        email: str,
        first_name: str | None,
        last_name: str | None,
    ) -> dict:
        """Create a customer record (demo mode)"""
        return {
            "customer_id": f"cust_{hashlib.md5(email.encode()).hexdigest()[:12]}",
            "email": email,
            "first_name": first_name or "",
            "last_name": last_name or "",
        }
    
    async def sync_catalog(self, merchant_id: UUID) -> int:
        """Sync catalog from Shopify, return count of products synced"""
        products = self._generate_products(merchant_id)
        return len(products)
    
    async def is_connected(self, merchant_id: UUID) -> bool:
        """Check if Shopify is connected for this merchant"""
        # Demo client is always "connected"
        return True
