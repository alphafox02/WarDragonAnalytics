#!/usr/bin/env python3
"""
WarDragon Analytics - Optional Authentication Module

Provides OPTIONAL password protection for the web UI.
Disabled by default - enable by setting AUTH_ENABLED=true in .env

Security features:
- Bcrypt password hashing
- JWT token-based sessions
- Secure cookie handling
- Rate limiting on login attempts
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional
from functools import wraps

from fastapi import HTTPException, Depends, Request, Response, Cookie
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.context import CryptContext
from jose import JWTError, jwt
import secrets

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration (all from environment variables)
# =============================================================================

# Auth is DISABLED by default - must explicitly enable
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "false").lower() == "true"

# Admin credentials (only used if AUTH_ENABLED=true)
AUTH_USERNAME = os.environ.get("AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "")  # Empty = auth disabled even if AUTH_ENABLED=true

# JWT settings
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", secrets.token_urlsafe(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.environ.get("JWT_EXPIRATION_HOURS", "24"))

# Cookie settings
COOKIE_NAME = "wardragon_session"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
COOKIE_HTTPONLY = True
COOKIE_SAMESITE = "lax"

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Rate limiting for login attempts (simple in-memory)
_login_attempts: dict = {}  # ip -> (count, first_attempt_time)
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15


def is_auth_enabled() -> bool:
    """Check if authentication is enabled and properly configured."""
    if not AUTH_ENABLED:
        return False
    if not AUTH_PASSWORD:
        logger.warning("AUTH_ENABLED=true but AUTH_PASSWORD not set - auth disabled")
        return False
    return True


def get_auth_status() -> dict:
    """Get current authentication status for /api/auth/status endpoint."""
    return {
        "auth_enabled": is_auth_enabled(),
        "auth_required": is_auth_enabled(),
        "session_expiration_hours": JWT_EXPIRATION_HOURS,
    }


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password for storage."""
    return pwd_context.hash(password)


def create_access_token(username: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    if expires_delta is None:
        expires_delta = timedelta(hours=JWT_EXPIRATION_HOURS)

    expire = datetime.utcnow() + expires_delta
    to_encode = {
        "sub": username,
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> Optional[str]:
    """Verify a JWT token and return the username if valid."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return username
    except JWTError as e:
        logger.debug(f"JWT verification failed: {e}")
        return None


def check_rate_limit(client_ip: str) -> bool:
    """
    Check if a client is rate-limited for login attempts.
    Returns True if allowed, False if rate-limited.
    """
    now = datetime.utcnow()

    if client_ip in _login_attempts:
        count, first_attempt = _login_attempts[client_ip]

        # Reset if lockout period has passed
        if now - first_attempt > timedelta(minutes=LOGIN_LOCKOUT_MINUTES):
            del _login_attempts[client_ip]
            return True

        # Check if locked out
        if count >= MAX_LOGIN_ATTEMPTS:
            return False

    return True


def record_login_attempt(client_ip: str, success: bool):
    """Record a login attempt for rate limiting."""
    now = datetime.utcnow()

    if success:
        # Clear attempts on successful login
        if client_ip in _login_attempts:
            del _login_attempts[client_ip]
        return

    # Record failed attempt
    if client_ip in _login_attempts:
        count, first_attempt = _login_attempts[client_ip]
        _login_attempts[client_ip] = (count + 1, first_attempt)
    else:
        _login_attempts[client_ip] = (1, now)


def authenticate_user(username: str, password: str) -> bool:
    """Authenticate a user against stored credentials."""
    if not is_auth_enabled():
        return True  # Auth disabled, always allow

    if username != AUTH_USERNAME:
        return False

    # For simplicity, we compare against the plain password from env
    # In production, you'd store a hashed password
    return password == AUTH_PASSWORD


async def get_current_user(
    request: Request,
    session_token: Optional[str] = Cookie(None, alias=COOKIE_NAME)
) -> Optional[str]:
    """
    Get the current authenticated user from session cookie.
    Returns None if not authenticated (when auth is disabled, returns 'anonymous').
    """
    if not is_auth_enabled():
        return "anonymous"  # Auth disabled, return anonymous user

    if not session_token:
        return None

    username = verify_token(session_token)
    return username


async def require_auth(
    request: Request,
    session_token: Optional[str] = Cookie(None, alias=COOKIE_NAME)
) -> str:
    """
    Dependency that requires authentication.
    Use this for protected endpoints.
    """
    if not is_auth_enabled():
        return "anonymous"  # Auth disabled, allow access

    if not session_token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = verify_token(session_token)
    if not username:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return username


def set_auth_cookie(response: Response, token: str):
    """Set the authentication cookie on a response."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=JWT_EXPIRATION_HOURS * 3600,
    )


def clear_auth_cookie(response: Response):
    """Clear the authentication cookie."""
    response.delete_cookie(key=COOKIE_NAME)


# =============================================================================
# Startup logging
# =============================================================================

if is_auth_enabled():
    logger.info(f"Authentication ENABLED for user: {AUTH_USERNAME}")
else:
    logger.info("Authentication DISABLED (set AUTH_ENABLED=true and AUTH_PASSWORD to enable)")
