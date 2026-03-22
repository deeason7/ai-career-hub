"""Central rate-limiter instance shared across all routers."""
import os

from slowapi import Limiter
from slowapi.util import get_remote_address

# When TESTING=true (set in CI), override all per-endpoint limits with a very
# high cap so tests never hit limits. In production, no default limit is set
# and per-endpoint decorators control each route individually.
_testing = os.getenv("TESTING", "false").lower() == "true"
_default_limits = ["10000/minute"] if _testing else []

limiter = Limiter(key_func=get_remote_address, default_limits=_default_limits)
