from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db, UserTokens
from ms_graph_service import MSGraphService
from datetime import datetime, timedelta
import logging
import os
from fastapi.responses import RedirectResponse
from urllib.parse import quote
import base64
import json
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()
graph_service = MSGraphService()

# Helpers to decode JWT (no signature verification) and log claims
def _decode_jwt_no_verify(token: str) -> dict:
    try:
        if not token or token.count('.') < 2:
            return {}
        payload_b64 = token.split('.')[1]
        padding = '=' * (-len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(payload_b64 + padding).decode('utf-8')
        return json.loads(payload_json)
    except Exception:
        return {}

def _log_access_token_claims(access_token: str, source: str):
    try:
        claims = _decode_jwt_no_verify(access_token)
        scp = claims.get('scp')
        roles = claims.get('roles')
        aud = claims.get('aud')
        tid = claims.get('tid')
        oid = claims.get('oid')
        upn = claims.get('upn') or claims.get('preferred_username')
        logger.info(f"Token claims [{source}]: scp={scp} roles={roles} aud={aud} tid={tid} oid={oid} upn={upn}")
    except Exception:
        logger.info(f"Token claims [{source}]: unavailable")

REQUIRED_GRAPH_SCOPES = {
    "OnlineMeetingTranscript.Read.All",
}

def _warn_if_required_scopes_missing(access_token: str, source: str):
    """Decode token scopes and warn if required Graph scopes are missing.
    This helps catch missing admin consent or incomplete user consent.
    """
    try:
        claims = _decode_jwt_no_verify(access_token)
        scp_raw = claims.get("scp") or ""
        token_scopes = set(scp_raw.split()) if isinstance(scp_raw, str) else set()
        missing = [s for s in REQUIRED_GRAPH_SCOPES if s not in token_scopes]
        if missing:
            logger.warning(
                f"Access token missing required Graph scopes [{source}]: missing={missing}. "
                f"Grant admin consent and have the user re-login to acquire updated scopes."
            )
        else:
            logger.info(f"All required Graph scopes present in access token [{source}]")
    except Exception as e:
        logger.warning(f"Unable to validate required scopes [{source}]: {e}")

@router.get("/login")
async def login():
    """Get Microsoft OAuth2 login URL"""
    try:
        auth_url = graph_service.get_authorization_url()
        return {"auth_url": auth_url}
    except Exception as e:
        logger.exception(f"Error generating auth URL: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate authorization URL: {str(e)}"
        )

@router.get("/callback")
async def auth_callback(
    code: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Handle OAuth2 callback and store tokens"""
    try:
        # If the identity provider returned an error, surface it clearly
        if error:
            msg = f"{error}: {error_description}" if error_description else error
            logger.error(f"Auth callback error from provider: {msg}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Authentication failed: {msg}"
            )

        if not code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing authorization code"
            )

        # Exchange code for tokens
        token_data = await graph_service.get_token_from_code(code)
        
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        
        # Calculate expiry time
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        # Log scopes and claims for diagnostics
        try:
            logger.info(f"MSAL scope string (callback): {token_data.get('scope')}")
        except Exception:
            pass
        _log_access_token_claims(access_token, "callback")
        _warn_if_required_scopes_missing(access_token, "callback")
        
        # Get user info to identify the user
        user_info = await get_user_profile(access_token)
        user_id = user_info["id"]
        
        # Store or update tokens
        user_tokens = db.query(UserTokens).filter(UserTokens.user_id == user_id).first()
        
        if user_tokens:
            user_tokens.access_token = access_token
            user_tokens.refresh_token = refresh_token
            user_tokens.expires_at = expires_at
            user_tokens.updated_at = datetime.utcnow()
        else:
            user_tokens = UserTokens(
                user_id=user_id,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at
            )
            db.add(user_tokens)
        
        db.commit()
        
        logger.info(f"Stored tokens for user {user_id}")
        
        # If FRONTEND_URL is configured, redirect back to the frontend with user info
        frontend_url = os.getenv("FRONTEND_URL")
        if frontend_url:
            display_name = user_info.get("displayName", "")
            mail = user_info.get("mail") or user_info.get("userPrincipalName") or ""
            redirect_url = (
                f"{frontend_url.rstrip('/')}/auth/signed-in"
                f"?user_id={user_info['id']}"
                f"&displayName={quote(display_name)}"
                f"&mail={quote(mail)}"
            )
            return RedirectResponse(url=redirect_url, status_code=302)
        
        # Fallback to JSON response if no frontend redirect is configured
        return {
            "message": "Authentication successful",
            "user": {
                "id": user_info["id"],
                "displayName": user_info["displayName"],
                "mail": user_info["mail"]
            }
        }
        
    except HTTPException as he:
        # Preserve HTTP errors raised above
        raise he
    except Exception as e:
        logger.exception(f"Authentication failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Authentication failed: {str(e)}"
        )

async def get_user_profile(access_token: str):
    """Get user profile from Microsoft Graph"""
    import httpx
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    url = "https://graph.microsoft.com/v1.0/me"
    
    async with httpx.AsyncClient(timeout=graph_service.http_timeout) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

@router.post("/refresh")
async def refresh_token(user_id: str, db: Session = Depends(get_db)):
    """Refresh access token"""
    try:
        user_tokens = db.query(UserTokens).filter(UserTokens.user_id == user_id).first()
        
        if not user_tokens or not user_tokens.refresh_token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No refresh token found for user"
            )
        
        # Check if token is expired or expiring soon
        if user_tokens.expires_at > datetime.utcnow() + timedelta(minutes=5):
            return {
                "message": "Token is still valid",
                "expires_at": user_tokens.expires_at
            }
        
        # Refresh the token
        token_data = await graph_service.refresh_access_token(user_tokens.refresh_token)
        
        access_token = token_data["access_token"]
        new_refresh_token = token_data.get("refresh_token", user_tokens.refresh_token)
        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        # Log scopes and claims for diagnostics
        try:
            logger.info(f"MSAL scope string (refresh): {token_data.get('scope')}")
        except Exception:
            pass
        _log_access_token_claims(access_token, "refresh_route")
        _warn_if_required_scopes_missing(access_token, "refresh_route")
        
        # Update stored tokens
        user_tokens.access_token = access_token
        user_tokens.refresh_token = new_refresh_token
        user_tokens.expires_at = expires_at
        user_tokens.updated_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Refreshed tokens for user {user_id}")
        
        return {
            "message": "Token refreshed successfully",
            "expires_at": expires_at
        }
        
    except Exception as e:
        logger.error(f"Error refreshing token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to refresh token: {str(e)}"
        )

@router.get("/status/{user_id}")
async def get_auth_status(user_id: str, db: Session = Depends(get_db)):
    """Check authentication status for a user"""
    user_tokens = db.query(UserTokens).filter(UserTokens.user_id == user_id).first()
    
    if not user_tokens:
        return {"authenticated": False, "message": "User not found"}
    
    # Check if token is valid
    is_expired = user_tokens.expires_at < datetime.utcnow()
    
    return {
        "authenticated": not is_expired,
        "user_id": user_id,
        "expires_at": user_tokens.expires_at,
        "needs_refresh": is_expired
    }

def get_valid_token(user_id: str, db: Session) -> str:
    """Get a valid access token for the user, refreshing if necessary"""
    user_tokens = db.query(UserTokens).filter(UserTokens.user_id == user_id).first()
    
    if not user_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated"
        )
    
    # Check if token is expired or expiring soon
    if user_tokens.expires_at < datetime.utcnow() + timedelta(minutes=5):
        # Try to refresh the token
        try:
            import asyncio
            token_data = asyncio.run(graph_service.refresh_access_token(user_tokens.refresh_token))
            
            access_token = token_data["access_token"]
            new_refresh_token = token_data.get("refresh_token", user_tokens.refresh_token)
            expires_in = token_data.get("expires_in", 3600)
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

            # Log scopes and claims for diagnostics
            try:
                logger.info(f"MSAL scope string (get_valid_token refresh): {token_data.get('scope')}")
            except Exception:
                pass
            _log_access_token_claims(access_token, "get_valid_token_refresh")
            _warn_if_required_scopes_missing(access_token, "get_valid_token_refresh")
            
            user_tokens.access_token = access_token
            user_tokens.refresh_token = new_refresh_token
            user_tokens.expires_at = expires_at
            user_tokens.updated_at = datetime.utcnow()
            
            db.commit()
            
            return access_token
            
        except Exception as e:
            logger.error(f"Failed to refresh token for user {user_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired and refresh failed"
            )
    
    return user_tokens.access_token

async def async_get_valid_token(user_id: str, db: Session) -> str:
    """Async version of get_valid_token to be used inside async routes."""
    user_tokens = db.query(UserTokens).filter(UserTokens.user_id == user_id).first()
    
    if not user_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated"
        )
    
    # Check if token is expired or expiring soon
    if user_tokens.expires_at < datetime.utcnow() + timedelta(minutes=5):
        # Try to refresh the token without blocking the event loop
        try:
            token_data = await graph_service.refresh_access_token(user_tokens.refresh_token)
            
            access_token = token_data["access_token"]
            new_refresh_token = token_data.get("refresh_token", user_tokens.refresh_token)
            expires_in = token_data.get("expires_in", 3600)
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

            # Log scopes and claims for diagnostics
            try:
                logger.info(f"MSAL scope string (async_get_valid_token refresh): {token_data.get('scope')}")
            except Exception:
                pass
            _log_access_token_claims(access_token, "async_get_valid_token_refresh")
            _warn_if_required_scopes_missing(access_token, "async_get_valid_token_refresh")
            
            user_tokens.access_token = access_token
            user_tokens.refresh_token = new_refresh_token
            user_tokens.expires_at = expires_at
            user_tokens.updated_at = datetime.utcnow()
            
            db.commit()
            
            return access_token
            
        except Exception as e:
            logger.error(f"Failed to refresh token for user {user_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired and refresh failed"
            )
    
    return user_tokens.access_token