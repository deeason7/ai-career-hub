"""Central rate-limiter instance shared across all routers."""
from slowapi import Limiter
from slowapi.util import get_remote_address

# Key by IP address — works for both authenticated and unauthenticated endpoints.
limiter = Limiter(key_func=get_remote_address)
