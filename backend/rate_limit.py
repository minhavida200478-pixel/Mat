"""Shared slowapi limiter (used by server.py and auth_router.py).

Kept in its own module so the auth routes can be extracted out of server.py
without creating a circular import between the two.
"""
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _client_ip_key(request: Request) -> str:
    """Rate-limit key that respects the reverse proxy.

    Behind the Kubernetes ingress, request.client.host is the proxy IP, which would
    lump every user into one bucket. Prefer the first hop in X-Forwarded-For (the
    real client) and fall back to the direct peer address otherwise.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return get_remote_address(request)


limiter = Limiter(key_func=_client_ip_key)
