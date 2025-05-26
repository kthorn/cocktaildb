import json
import logging
import time
import urllib.request
from typing import Any, Dict, Optional

from jose import jwk
from jose import jwt as jose_jwt
from jose.utils import base64url_decode

logger = logging.getLogger()

# Cache the keys to avoid fetching them for every request
_JWKS_CACHE = {}
_JWKS_TIMESTAMP = 0
_JWKS_EXPIRY = 3600  # Cache JWKs for 1 hour


def get_cognito_jwks(region: str, user_pool_id: str) -> Dict:
    """
    Fetch the JSON Web Key Set (JWKS) from AWS Cognito
    """
    global _JWKS_CACHE, _JWKS_TIMESTAMP

    # Check if we have a valid cached version
    current_time = time.time()
    if _JWKS_CACHE and current_time - _JWKS_TIMESTAMP < _JWKS_EXPIRY:
        return _JWKS_CACHE

    # Fetch new JWKs
    keys_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"
    try:
        with urllib.request.urlopen(keys_url) as response:
            jwks = json.loads(response.read())
            _JWKS_CACHE = jwks
            _JWKS_TIMESTAMP = current_time
            return jwks
    except Exception as e:
        logger.error(f"Error fetching JWKs from Cognito: {str(e)}")
        raise


def verify_token(
    token: str, region: str, user_pool_id: str, app_client_id: str
) -> Dict[str, Any]:
    """
    Verify the JWT token from AWS Cognito
    """
    # Get the key id from the token header
    try:
        headers = jose_jwt.get_unverified_headers(token)
    except Exception as e:
        logger.error(f"Invalid token header: {str(e)}")
        raise Exception("Invalid token")

    kid = headers.get("kid")
    if not kid:
        raise Exception("Token header missing 'kid'")

    # Get the JWKs from Cognito
    jwks = get_cognito_jwks(region, user_pool_id)
    key = None

    # Find the right key
    for jwk_key in jwks.get("keys", []):
        if jwk_key.get("kid") == kid:
            key = jwk_key
            break

    if not key:
        raise Exception(f"Public key with kid {kid} not found in JWKS")

    # Get the public key
    public_key = jwk.construct(key)

    # Get message and signature (encoded in base64)
    message, encoded_signature = token.rsplit(".", 1)
    decoded_signature = base64url_decode(encoded_signature.encode("utf-8"))

    # Verify the signature
    if not public_key.verify(message.encode("utf8"), decoded_signature):
        raise Exception("Signature verification failed")

    # Verify the claims
    claims = jose_jwt.get_unverified_claims(token)

    # Verify expiration
    if time.time() > claims["exp"]:
        raise Exception("Token is expired")

    # Verify audience (use_pool/app client)
    token_use = claims.get("token_use")
    if token_use == "access":
        client_id = claims.get("client_id")
        if client_id != app_client_id:
            raise Exception(f"Token was not issued for this client id: {client_id}")
    elif token_use == "id":
        audience = claims.get("aud")
        if audience != app_client_id:
            raise Exception(f"Token was not issued for this audience: {audience}")
    else:
        raise Exception(f"Invalid token use: {token_use}")

    # Verify issuer
    iss = claims.get("iss")
    expected_iss = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
    if iss != expected_iss:
        raise Exception(f"Invalid issuer: {iss}, expected: {expected_iss}")

    return claims


def extract_token_from_header(auth_header: str) -> str:
    """
    Extract the token from the Authorization header
    """
    if not auth_header:
        raise Exception("Authorization header is missing")

    parts = auth_header.split()

    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise Exception('Authorization header must be in format "Bearer token"')

    return parts[1]


def get_user_from_event(
    event: Dict, region: str, user_pool_id: str, app_client_id: str
) -> Optional[Dict]:
    """
    Extract and verify user information from API Gateway event
    """
    try:
        # Get the token from the Authorization header
        auth_header = event.get("headers", {}).get("Authorization") or event.get(
            "headers", {}
        ).get("authorization")
        if not auth_header:
            return None

        # Extract token
        token = extract_token_from_header(auth_header)

        # Verify token
        claims = verify_token(token, region, user_pool_id, app_client_id)

        # Return user info
        return {
            "user_id": claims.get("sub"),
            "username": claims.get("username", claims.get("cognito:username")),
            "email": claims.get("email"),
            "groups": claims.get("cognito:groups", []),
            "claims": claims,
        }
    except Exception as e:
        logger.warning(f"Failed to extract user from event: {str(e)}")
        return None
