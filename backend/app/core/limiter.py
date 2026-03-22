"""Central rate-limiter instance shared across all routers."""
import os
from typing import Callable

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# When TESTING=true (CI), return a no-op decorator so @limiter.limit()
# per-endpoint limits don't fire — default_limits doesn't override them.
_testing = os.getenv("TESTING", "false").lower() == "true"


def rate_limit(limit_string: str) -> Callable:
    """Apply a slowapi rate limit; full no-op when TESTING=true."""
    if _testing:
        return lambda f: f  # pass-through, no rate limit applied
    return limiter.limit(limit_string)
