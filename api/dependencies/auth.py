import logging
import os
import time
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import requests

logger = logging.getLogger(__name__)

# HTTP Bearer token security scheme
security = HTTPBearer(auto_error=False)

# Cache for Cognito JWKS (JSON Web Key Set)
_jwks_cache: Dict[str, Any] = {}
_jwks_cache_time: float = 0
JWKS_CACHE_DURATION = 3600  # 1 hour


class UserInfo:
    """User information extracted from Cognito JWT token"""

    def __init__(self, user_id: str, username: Optional[str] = None,
                 email: Optional[str] = None, groups: Optional[list] = None,
                 claims: Optional[Dict[str, Any]] = None):
        self.user_id = user_id
        self.username = username
        self.email = email
        self.groups = groups or []
        self.claims = claims or {}


def get_cognito_jwks() -> Dict[str, Any]:
    """Fetch and cache Cognito JWKS for JWT validation"""
    global _jwks_cache, _jwks_cache_time

    current_time = time.time()
    if _jwks_cache and (current_time - _jwks_cache_time) < JWKS_CACHE_DURATION:
        return _jwks_cache

    user_pool_id = os.environ.get("USER_POOL_ID")
    if not user_pool_id:
        raise ValueError("USER_POOL_ID environment variable not set")

    region = user_pool_id.split("_")[0]
    jwks_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"

    try:
        response = requests.get(jwks_url, timeout=5)
        response.raise_for_status()
        _jwks_cache = response.json()
        _jwks_cache_time = current_time
        logger.info(f"Fetched Cognito JWKS from {jwks_url}")
        return _jwks_cache
    except Exception as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        if _jwks_cache:
            return _jwks_cache
        raise


def get_signing_key(token: str) -> Any:
    """Get the signing key for a JWT token from Cognito JWKS"""
    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise ValueError("Token missing 'kid' header")

        jwks = get_cognito_jwks()
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return jwt.algorithms.RSAAlgorithm.from_jwk(key)

        raise ValueError(f"Unable to find signing key for kid: {kid}")
    except Exception as e:
        logger.error(f"Error getting signing key: {e}")
        raise


def validate_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """Validate a Cognito JWT token and return claims"""
    try:
        user_pool_id = os.environ.get("USER_POOL_ID")
        client_id = os.environ.get("APP_CLIENT_ID")

        if not user_pool_id or not client_id:
            logger.error("USER_POOL_ID or APP_CLIENT_ID not configured")
            return None

        region = user_pool_id.split("_")[0]
        issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"

        signing_key = get_signing_key(token)

        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=issuer,
            options={
                "verify_aud": False,  # Cognito uses client_id in different claim
                "verify_exp": True,
            }
        )

        # Verify client_id (Cognito puts it in 'aud' for id_token or 'client_id' for access_token)
        token_client_id = claims.get("aud") or claims.get("client_id")
        if token_client_id != client_id:
            logger.warning(f"Token client_id mismatch: {token_client_id} != {client_id}")
            return None

        return claims

    except jwt.ExpiredSignatureError:
        logger.warning("JWT token has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        return None
    except Exception as e:
        logger.error(f"Error validating JWT: {e}")
        return None


def get_user_from_jwt(request: Request, credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[UserInfo]:
    """Extract user information from JWT Bearer token"""
    if not credentials:
        logger.debug("No authorization credentials provided")
        return None

    token = credentials.credentials
    claims = validate_jwt_token(token)

    if not claims:
        return None

    user_id = claims.get("sub")
    if not user_id:
        logger.warning("No 'sub' claim found in JWT")
        return None

    username = claims.get("username") or claims.get("cognito:username")
    email = claims.get("email")
    groups_claim = claims.get("cognito:groups", [])
    groups = groups_claim if isinstance(groups_claim, list) else groups_claim.split(",") if groups_claim else []

    logger.debug(f"Authenticated user: {user_id}, groups: {groups}")

    return UserInfo(
        user_id=user_id,
        username=username,
        email=email,
        groups=groups,
        claims=claims
    )


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[UserInfo]:
    """Get current user information if available (optional authentication)

    Validates JWT from Authorization header.
    """
    return get_user_from_jwt(request, credentials)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> UserInfo:
    """Get current user information (required authentication)"""
    user = await get_current_user_optional(request, credentials)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_authentication(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> UserInfo:
    """Require authentication - raises exception if user is not authenticated"""
    return await get_current_user(request, credentials)


def is_admin(user: UserInfo) -> bool:
    """Check if user is an admin"""
    return "admin" in user.groups


def is_editor(user: UserInfo) -> bool:
    """Check if user is an editor"""
    return "editor" in user.groups


def is_editor_or_admin(user: UserInfo) -> bool:
    """Check if user is an editor or admin"""
    return is_editor(user) or is_admin(user)


async def require_editor_access(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> UserInfo:
    """Require editor or admin access - raises exception if user is not authorized"""
    user = await get_current_user(request, credentials)

    if not is_editor_or_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Editor access required. Only editors and admins can create, edit, or delete recipes and ingredients.",
        )

    return user
