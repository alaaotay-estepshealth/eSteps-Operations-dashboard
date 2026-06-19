"""Shared slowapi limiter.

Enabled only in production so local dev and the test suite (which hammer
`/auth/token`) are unaffected. Brute-force protection is a production concern;
behind a reverse proxy, set the proxy to pass a real client IP.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.environment == "production",
)
