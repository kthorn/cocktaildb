import logging
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..auth import verify_token, extract_token_from_header
from ..core.config import settings

logger = logging.getLogger(__name__)

# OAuth2 scheme for token extraction
security = HTTPBearer(auto_error=False)


class UserInfo:
    """User information extracted from JWT token"""
    
    def __init__(self, user_id: str, username: Optional[str] = None, 
                 email: Optional[str] = None, groups: Optional[list] = None,
                 claims: Optional[Dict[str, Any]] = None):
        self.user_id = user_id
        self.username = username
        self.email = email
        self.groups = groups or []
        self.claims = claims or {}


async def get_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[str]:
    """Extract token from Authorization header"""
    if not credentials:
        return None
    return credentials.credentials


async def get_current_user_optional(token: Optional[str] = Depends(get_token)) -> Optional[UserInfo]:
    """Get current user information if token is provided (optional authentication)"""
    if not token:
        return None
    
    try:
        claims = verify_token(
            token=token,
            region=settings.aws_region,
            user_pool_id=settings.user_pool_id,
            app_client_id=settings.app_client_id
        )
        
        return UserInfo(
            user_id=claims.get("sub"),
            username=claims.get("username", claims.get("cognito:username")),
            email=claims.get("email"),
            groups=claims.get("cognito:groups", []),
            claims=claims
        )
    except Exception as e:
        logger.warning(f"Failed to verify token: {str(e)}")
        return None


async def get_current_user(token: Optional[str] = Depends(get_token)) -> UserInfo:
    """Get current user information (required authentication)"""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        claims = verify_token(
            token=token,
            region=settings.aws_region,
            user_pool_id=settings.user_pool_id,
            app_client_id=settings.app_client_id
        )
        
        return UserInfo(
            user_id=claims.get("sub"),
            username=claims.get("username", claims.get("cognito:username")),
            email=claims.get("email"),
            groups=claims.get("cognito:groups", []),
            claims=claims
        )
    except Exception as e:
        logger.warning(f"Token verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_authentication(user: Optional[UserInfo] = Depends(get_current_user_optional)) -> UserInfo:
    """Require authentication - raises exception if user is not authenticated"""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user