"""
Exception hierarchy for Agent Commerce SDK
"""


class AgentCommerceError(Exception):
    """Base exception for all Agent Commerce errors"""
    
    def __init__(self, message: str, code: str = "agent_commerce_error", metadata: dict | None = None):
        self.message = message
        self.code = code
        self.metadata = metadata or {}
        super().__init__(self.message)


class ConfigurationError(AgentCommerceError):
    """Configuration or environment error"""
    
    def __init__(self, message: str, missing_var: str | None = None):
        metadata = {"missing_var": missing_var} if missing_var else {}
        super().__init__(message, code="configuration_error", metadata=metadata)


class AuthenticationError(AgentCommerceError):
    """Authentication failure"""
    
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, code="authentication_error")


class AuthorizationError(AgentCommerceError):
    """Authorization failure - user lacks permission"""
    
    def __init__(self, message: str = "Access denied", required_scope: str | None = None):
        metadata = {"required_scope": required_scope} if required_scope else {}
        super().__init__(message, code="authorization_error", metadata=metadata)


class NotFoundError(AgentCommerceError):
    """Resource not found"""
    
    def __init__(self, resource_type: str, resource_id: str):
        message = f"{resource_type} not found: {resource_id}"
        metadata = {"resource_type": resource_type, "resource_id": resource_id}
        super().__init__(message, code="not_found", metadata=metadata)


class ConflictError(AgentCommerceError):
    """Resource conflict - e.g., duplicate idempotency key with different payload"""
    
    def __init__(self, message: str, existing_resource: dict | None = None):
        metadata = {"existing_resource": existing_resource} if existing_resource else {}
        super().__init__(message, code="conflict", metadata=metadata)


class ValidationError(AgentCommerceError):
    """Input validation failed"""
    
    def __init__(self, message: str, field: str | None = None, details: list | None = None):
        metadata = {}
        if field:
            metadata["field"] = field
        if details:
            metadata["details"] = details
        super().__init__(message, code="validation_error", metadata=metadata)


class PaymentError(AgentCommerceError):
    """Payment processing error"""
    
    def __init__(self, message: str, razorpay_code: str | None = None):
        metadata = {"razorpay_code": razorpay_code} if razorpay_code else {}
        super().__init__(message, code="payment_error", metadata=metadata)


class PolicyViolationError(AgentCommerceError):
    """Policy evaluation denied the action"""
    
    def __init__(self, message: str, rule_id: str | None = None, decision: str | None = None):
        metadata = {}
        if rule_id:
            metadata["rule_id"] = rule_id
        if decision:
            metadata["decision"] = decision
        super().__init__(message, code="policy_violation", metadata=metadata)


class ShopifyError(AgentCommerceError):
    """Shopify API error"""
    
    def __init__(self, message: str, status_code: int | None = None, graphql_errors: list | None = None):
        metadata = {}
        if status_code:
            metadata["status_code"] = status_code
        if graphql_errors:
            metadata["graphql_errors"] = graphql_errors
        super().__init__(message, code="shopify_error", metadata=metadata)


class RazorpayError(AgentCommerceError):
    """Razorpay API error"""
    
    def __init__(self, message: str, status_code: int | None = None, razorpay_code: str | None = None):
        metadata = {}
        if status_code:
            metadata["status_code"] = status_code
        if razorpay_code:
            metadata["razorpay_code"] = razorpay_code
        super().__init__(message, code="razorpay_error", metadata=metadata)
