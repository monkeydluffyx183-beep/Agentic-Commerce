"""
Razorpay API client

Handles orders, payments, verification, and webhook signature validation.
Test mode only - never use live/production credentials.
"""

import base64
import hashlib
import hmac
import os
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

import httpx

from ..core.errors import ConfigurationError, PaymentError, RazorpayError
from ..core.protocols import RazorpayPort


class RazorpayClient:
    """
    Real Razorpay API client (TEST MODE ONLY)
    
    Requires:
    - RAZORPAY_KEY_ID
    - RAZORPAY_KEY_SECRET
    - Optional: RAZORPAY_WEBHOOK_SECRET for webhook verification
    """
    
    BASE_URL = "https://api.razorpay.com/v1"
    
    def __init__(
        self,
        key_id: str | None = None,
        key_secret: str | None = None,
        webhook_secret: str | None = None,
    ):
        self.key_id = key_id or os.getenv("RAZORPAY_KEY_ID")
        self.key_secret = key_secret or os.getenv("RAZORPAY_KEY_SECRET")
        self.webhook_secret = webhook_secret or os.getenv("RAZORPAY_WEBHOOK_SECRET")
        
        self._auth: Optional[str] = None
        if self.key_id and self.key_secret:
            credentials = f"{self.key_id}:{self.key_secret}"
            self._auth = base64.b64encode(credentials.encode()).decode()
    
    @property
    def is_configured(self) -> bool:
        """Check if Razorpay credentials are configured"""
        return self._auth is not None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get authenticated HTTP client"""
        if not self._auth:
            raise ConfigurationError(
                "Razorpay not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.",
                missing_var="RAZORPAY_*",
            )
        
        return httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Basic {self._auth}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
    
    async def create_order(
        self,
        merchant_id: UUID,
        amount: Decimal,
        currency: str,
        receipt_id: str,
        notes: dict | None = None,
    ) -> dict:
        """Create a Razorpay order"""
        client = await self._get_client()
        
        # Amount in smallest currency unit (paise for INR)
        amount_paise = int(amount * 100)
        
        payload = {
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt_id,
            "notes": notes or {},
        }
        
        try:
            response = await client.post("/orders", json=payload)
            response.raise_for_status()
            data = response.json()
            
            return {
                "order_id": data["id"],
                "amount": Decimal(str(data["amount"])) / 100,
                "currency": data["currency"],
                "status": data["status"],
                "receipt": data.get("receipt"),
                "notes": data.get("notes", {}),
                "created_at": data.get("created_at"),
            }
        except httpx.HTTPStatusError as e:
            error_data = e.response.json() if e.response.content else {}
            raise RazorpayError(
                f"Failed to create Razorpay order: {error_data.get('description', str(e))}",
                status_code=e.response.status_code,
                razorpay_code=error_data.get("code"),
            )
        finally:
            await client.aclose()
    
    async def fetch_order(self, merchant_id: UUID, order_id: str) -> dict:
        """Fetch order details from Razorpay"""
        client = await self._get_client()
        
        try:
            response = await client.get(f"/orders/{order_id}")
            response.raise_for_status()
            data = response.json()
            
            return {
                "order_id": data["id"],
                "amount": Decimal(str(data["amount"])) / 100,
                "currency": data["currency"],
                "status": data["status"],
                "receipt": data.get("receipt"),
                "notes": data.get("notes", {}),
                "created_at": data.get("created_at"),
                "attempts": data.get("attempts", 0),
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                from ..core.errors import NotFoundError
                raise NotFoundError("RazorpayOrder", order_id)
            error_data = e.response.json() if e.response.content else {}
            raise RazorpayError(
                f"Failed to fetch Razorpay order: {error_data.get('description', str(e))}",
                status_code=e.response.status_code,
            )
        finally:
            await client.aclose()
    
    async def capture_payment(
        self,
        merchant_id: UUID,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> dict:
        """Capture and verify a payment"""
        client = await self._get_client()
        
        # Verify signature first
        expected_signature = self._compute_signature(razorpay_order_id, razorpay_payment_id)
        if not hmac.compare_digest(razorpay_signature, expected_signature):
            raise PaymentError(
                "Invalid payment signature. Possible tampering.",
                razorpay_code="SIGNATURE_VERIFICATION_FAILED",
            )
        
        try:
            # Fetch payment to verify status
            response = await client.get(f"/payments/{razorpay_payment_id}")
            response.raise_for_status()
            payment_data = response.json()
            
            if payment_data.get("status") != "captured":
                raise PaymentError(
                    f"Payment not captured: {payment_data.get('status')}",
                    razorpay_code="PAYMENT_NOT_CAPTURED",
                )
            
            if payment_data.get("order_id") != razorpay_order_id:
                raise PaymentError(
                    "Payment order ID mismatch",
                    razorpay_code="ORDER_MISMATCH",
                )
            
            return {
                "payment_id": payment_data["id"],
                "order_id": payment_data["order_id"],
                "amount": Decimal(str(payment_data["amount"])) / 100,
                "currency": payment_data["currency"],
                "status": payment_data["status"],
                "method": payment_data.get("method"),
                "captured_at": payment_data.get("captured_at"),
                "notes": payment_data.get("notes", {}),
            }
        except httpx.HTTPStatusError as e:
            error_data = e.response.json() if e.response.content else {}
            raise RazorpayError(
                f"Failed to capture payment: {error_data.get('description', str(e))}",
                status_code=e.response.status_code,
            )
        finally:
            await client.aclose()
    
    async def fetch_payment(
        self,
        merchant_id: UUID,
        payment_id: str,
    ) -> dict:
        """Fetch payment details"""
        client = await self._get_client()
        
        try:
            response = await client.get(f"/payments/{payment_id}")
            response.raise_for_status()
            data = response.json()
            
            return {
                "payment_id": data["id"],
                "order_id": data.get("order_id"),
                "amount": Decimal(str(data["amount"])) / 100,
                "currency": data["currency"],
                "status": data["status"],
                "method": data.get("method"),
                "email": data.get("email"),
                "contact": data.get("contact"),
                "captured_at": data.get("captured_at"),
                "notes": data.get("notes", {}),
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                from ..core.errors import NotFoundError
                raise NotFoundError("RazorpayPayment", payment_id)
            error_data = e.response.json() if e.response.content else {}
            raise RazorpayError(
                f"Failed to fetch payment: {error_data.get('description', str(e))}",
                status_code=e.response.status_code,
            )
        finally:
            await client.aclose()
    
    async def refund_payment(
        self,
        merchant_id: UUID,
        payment_id: str,
        amount: Decimal,
        notes: dict | None = None,
    ) -> dict:
        """Refund a payment"""
        client = await self._get_client()
        
        payload = {
            "amount": int(amount * 100),
            "notes": notes or {},
        }
        
        try:
            response = await client.post(f"/payments/{payment_id}/refund", json=payload)
            response.raise_for_status()
            data = response.json()
            
            return {
                "refund_id": data["id"],
                "payment_id": data["payment_id"],
                "amount": Decimal(str(data["amount"])) / 100,
                "status": data["status"],
                "notes": data.get("notes", {}),
                "created_at": data.get("created_at"),
            }
        except httpx.HTTPStatusError as e:
            error_data = e.response.json() if e.response.content else {}
            raise RazorpayError(
                f"Failed to refund payment: {error_data.get('description', str(e))}",
                status_code=e.response.status_code,
            )
        finally:
            await client.aclose()
    
    async def verify_webhook_signature(
        self,
        merchant_id: UUID,
        payload: bytes,
        signature: str,
    ) -> bool:
        """Verify Razorpay webhook signature"""
        if not self.webhook_secret:
            raise ConfigurationError(
                "RAZORPAY_WEBHOOK_SECRET not configured for webhook verification.",
                missing_var="RAZORPAY_WEBHOOK_SECRET",
            )
        
        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    
    async def is_connected(self, merchant_id: UUID) -> bool:
        """Check if Razorpay is connected for this merchant"""
        if not self.is_configured:
            return False
        
        # Try to create a small test order
        try:
            await self.create_order(
                merchant_id=merchant_id,
                amount=Decimal("1"),
                currency="INR",
                receipt_id="connection_test",
            )
            return True
        except Exception:
            return False
    
    def _compute_signature(self, order_id: str, payment_id: str) -> str:
        """Compute expected signature for payment verification"""
        if not self.key_secret:
            raise ConfigurationError("RAZORPAY_KEY_SECRET not configured")
        
        message = f"{order_id}|{payment_id}"
        return hmac.new(
            self.key_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()


# Alias for protocol compliance
RazorpayPort = RazorpayClient
