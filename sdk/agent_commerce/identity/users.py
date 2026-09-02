"""
User management service

Handles user registration, authentication, and profile management.
First account becomes admin; subsequent accounts are customers.
"""

import hashlib
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from ..core.errors import AuthenticationError, AuthorizationError, ConflictError, NotFoundError
from ..core.types import User


class UserService:
    """
    User management service
    
    - First registered account becomes admin
    - Subsequent accounts are customers
    - Role is stored with the account, never sent in requests
    """
    
    def __init__(self, db_session=None):
        self.db = db_session  # Would be SQLAlchemy/asyncpg session
        self._users: dict[str, User] = {}  # In-memory for demo
    
    async def register(
        self,
        email: str,
        password: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> User:
        """Register a new user"""
        # Check if user exists
        for user in self._users.values():
            if user.email == email:
                raise ConflictError("Email already registered", field="email")
        
        # Determine role - first user is admin
        is_first_user = len(self._users) == 0
        role = "admin" if is_first_user else "customer"
        
        # Hash password (in production, use bcrypt/argon2)
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        now = datetime.now(timezone.utc)
        user_id = uuid4()
        
        user = User(
            user_id=user_id,
            email=email,
            role=role,
            created_at=now,
            updated_at=now,
            metadata={
                "first_name": first_name,
                "last_name": last_name,
                "password_hash": password_hash,
            },
        )
        
        self._users[str(user_id)] = user
        return user
    
    async def authenticate(self, email: str, password: str) -> User:
        """Authenticate user and return user record"""
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        for user in self._users.values():
            if user.email == email:
                stored_hash = user.metadata.get("password_hash")
                if stored_hash != password_hash:
                    raise AuthenticationError("Invalid credentials")
                return user
        
        raise AuthenticationError("Invalid credentials")
    
    async def get_by_id(self, user_id: UUID) -> User:
        """Get user by ID"""
        user = self._users.get(str(user_id))
        if not user:
            raise NotFoundError("User", str(user_id))
        return user
    
    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        for user in self._users.values():
            if user.email == email:
                return user
        return None
    
    async def is_admin(self, user_id: UUID) -> bool:
        """Check if user is admin"""
        user = await self.get_by_id(user_id)
        return user.role == "admin"
    
    async def require_admin(self, user_id: UUID) -> None:
        """Raise AuthorizationError if user is not admin"""
        if not await self.is_admin(user_id):
            raise AuthorizationError("Admin access required")
    
    async def list_users(self) -> list[User]:
        """List all users"""
        return list(self._users.values())
