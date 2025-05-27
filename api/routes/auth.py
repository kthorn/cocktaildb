"""Authentication endpoints for the CocktailDB API"""

import logging
from fastapi import APIRouter, Depends

from dependencies.auth import UserInfo, require_authentication
from models.responses import UserInfoResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(
    user: UserInfo = Depends(require_authentication)
):
    """Get current authenticated user information"""
    logger.info(f"Getting user info for user {user.user_id}")
    
    return UserInfoResponse(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        groups=user.groups
    )