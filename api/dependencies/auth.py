import logging
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status, Request

logger = logging.getLogger(__name__)


class UserInfo:
    """User information extracted from API Gateway Cognito Authorizer"""
    
    def __init__(self, user_id: str, username: Optional[str] = None, 
                 email: Optional[str] = None, groups: Optional[list] = None,
                 claims: Optional[Dict[str, Any]] = None):
        self.user_id = user_id
        self.username = username
        self.email = email
        self.groups = groups or []
        self.claims = claims or {}


def get_user_from_lambda_event(request: Request) -> Optional[UserInfo]:
    """Extract user information from Lambda event context (API Gateway Cognito Authorizer)"""
    try:
        # Import here to avoid circular import
        from main import _current_lambda_event
        event = _current_lambda_event
            
        if not event:
            logger.debug("No Lambda event found in global state")
            return None
            
        # Extract authorizer claims from API Gateway event
        authorizer_context = event.get("requestContext", {}).get("authorizer", {})
        claims = authorizer_context.get("claims")
        
        if not claims:
            logger.debug("No authorizer claims found in Lambda event")
            return None
            
        logger.info(f"Found authorizer claims: {list(claims.keys())}")
        
        # Extract user information from claims
        user_id = claims.get("sub")
        if not user_id:
            logger.warning("No 'sub' claim found in authorizer context")
            return None
            
        username = claims.get("username") or claims.get("cognito:username")
        email = claims.get("email")
        groups_str = claims.get("cognito:groups", "")
        groups = groups_str.split(",") if groups_str else []
        
        return UserInfo(
            user_id=user_id,
            username=username,
            email=email,
            groups=groups,
            claims=claims
        )
        
    except Exception as e:
        logger.error(f"Error extracting user from Lambda event: {str(e)}")
        return None


async def get_current_user_optional(request: Request) -> Optional[UserInfo]:
    """Get current user information if available (optional authentication)"""
    return get_user_from_lambda_event(request)


async def get_current_user(request: Request) -> UserInfo:
    """Get current user information (required authentication)"""
    user = get_user_from_lambda_event(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_authentication(request: Request) -> UserInfo:
    """Require authentication - raises exception if user is not authenticated"""
    user = get_user_from_lambda_event(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user