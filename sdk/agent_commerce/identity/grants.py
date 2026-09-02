"""
Agent grant management

Handles delegated authorization - granting agents permission to act on behalf of users.
Mechanically issues AgentGrant records that bind user_id -> agent_id with specific scopes.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from ..core.errors import AuthorizationError, NotFoundError, ValidationError
from ..core.types import PolicyDecisionStatus


class AgentGrant:
    """Delegated authorization grant"""
    
    def __init__(
        self,
        grant_id: UUID,
        user_id: UUID,
        agent_id: UUID,
        merchant_id: UUID,
        scopes: list[str],
        created_at: datetime,
        expires_at: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ):
        self.grant_id = grant_id
        self.user_id = user_id
        self.agent_id = agent_id
        self.merchant_id = merchant_id
        self.scopes = scopes
        self.created_at = created_at
        self.expires_at = expires_at
        self.metadata = metadata or {}
    
    @property
    def is_valid(self) -> bool:
        """Check if grant is still valid"""
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False
        return True
    
    @property
    def has_approval_decide_scope(self) -> bool:
        """Check if grant has approval:decide scope"""
        return "approval:decide" in self.scopes


class GrantService:
    """
    Agent grant management service
    
    - Issues grants binding user_id -> agent_id with scopes
    - Customers can only be assigned agents by admin
    - approval:decide scope is never granted to customer-assigned agents
    """
    
    # Default scopes for shopper agents
    SHOPPER_SCOPES = [
        "catalog:read",
        "inventory:read",
        "cart:write",
        "checkout:create",
        "payment:request",
        "order:read",
        "approval:read",
    ]
    
    # Growth agent scopes (disjoint from shopper)
    GROWTH_SCOPES = [
        "analytics:read",
        "campaign:write",
        "data:seed_write",
    ]
    
    def __init__(self, db_session=None):
        self.db = db_session
        self._grants: dict[str, AgentGrant] = {}  # In-memory for demo
    
    async def create_grant(
        self,
        user_id: UUID,
        agent_id: UUID,
        merchant_id: UUID,
        scopes: Optional[list[str]] = None,
        agent_kind: str = "shopper",
    ) -> AgentGrant:
        """Create a new agent grant"""
        # Validate scopes based on agent kind
        if scopes is None:
            if agent_kind == "shopper":
                scopes = self.SHOPPER_SCOPES.copy()
            elif agent_kind == "merchant_companion":
                scopes = self.GROWTH_SCOPES.copy()
            else:
                raise ValidationError(f"Unknown agent kind: {agent_kind}")
        
        # Security: Never grant approval:decide to customer-assigned agents
        # This is enforced at grant creation time
        if "approval:decide" in scopes and agent_kind == "shopper":
            raise AuthorizationError(
                "approval:decide scope cannot be granted to shopper agents"
            )
        
        now = datetime.now(timezone.utc)
        grant_id = uuid4()
        
        grant = AgentGrant(
            grant_id=grant_id,
            user_id=user_id,
            agent_id=agent_id,
            merchant_id=merchant_id,
            scopes=scopes,
            created_at=now,
            expires_at=None,  # No expiry by default
            metadata={"agent_kind": agent_kind},
        )
        
        self._grants[str(grant_id)] = grant
        return grant
    
    async def get_by_id(self, grant_id: UUID) -> AgentGrant:
        """Get grant by ID"""
        grant = self._grants.get(str(grant_id))
        if not grant:
            raise NotFoundError("Grant", str(grant_id))
        
        if not grant.is_valid:
            raise AuthorizationError("Grant has expired")
        
        return grant
    
    async def get_grant_for_agent_and_user(
        self,
        agent_id: UUID,
        user_id: UUID,
    ) -> Optional[AgentGrant]:
        """Get active grant for specific agent-user pair"""
        for grant in self._grants.values():
            if grant.agent_id == agent_id and grant.user_id == user_id:
                if grant.is_valid:
                    return grant
        return None
    
    async def revoke_grant(self, grant_id: UUID) -> None:
        """Revoke a grant"""
        grant = await self.get_by_id(grant_id)
        grant.expires_at = datetime.now(timezone.utc)
        self._grants[str(grant_id)] = grant
    
    async def list_grants(
        self,
        user_id: Optional[UUID] = None,
        agent_id: Optional[UUID] = None,
        merchant_id: Optional[UUID] = None,
    ) -> list[AgentGrant]:
        """List grants with optional filters"""
        grants = list(self._grants.values())
        
        if user_id:
            grants = [g for g in grants if g.user_id == user_id]
        if agent_id:
            grants = [g for g in grants if g.agent_id == agent_id]
        if merchant_id:
            grants = [g for g in grants if g.merchant_id == merchant_id]
        
        return [g for g in grants if g.is_valid]


class RequestContext:
    """Request context resolved from grant"""
    
    def __init__(
        self,
        user_id: UUID,
        merchant_id: UUID,
        agent_id: Optional[UUID],
        session_id: str,
        scopes: list[str],
        idempotency_key: Optional[str] = None,
    ):
        self.user_id = user_id
        self.merchant_id = merchant_id
        self.agent_id = agent_id
        self.session_id = session_id
        self.scopes = scopes
        self.idempotency_key = idempotency_key


async def resolve_request_context(
    grant: AgentGrant,
    session_id: str,
    idempotency_key: Optional[str] = None,
) -> RequestContext:
    """
    Resolve request context from a grant
    
    This is the core identity resolution function - sets user_id from grant.user_id
    so each customer's carts, checkouts, approvals are isolated.
    """
    if not grant.is_valid:
        raise AuthorizationError("Grant is not valid")
    
    return RequestContext(
        user_id=grant.user_id,
        merchant_id=grant.merchant_id,
        agent_id=grant.agent_id,
        session_id=session_id,
        scopes=grant.scopes,
        idempotency_key=idempotency_key,
    )
