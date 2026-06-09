"""Browser-cookie helpers.

The CookieController JS bridge isn't ready on the first render (it raises until
the browser hydrates it), so every cookie op is wrapped here. Centralizing the
guards means no caller can forget one — an unguarded write has broken login before.
"""


def cookie_get(manager, key: str):
    """Read a cookie value; None if the bridge isn't ready yet."""
    try:
        return manager.get(key)
    except Exception:
        return None


def cookie_set(manager, key: str, value: str, max_age: int = 3600) -> None:
    """Best-effort cookie write; a no-op if the bridge isn't ready."""
    try:
        manager.set(key, value, max_age=max_age)
    except Exception:
        pass


def cookie_remove(manager, key: str) -> None:
    """Best-effort cookie delete; a no-op if the bridge isn't ready."""
    try:
        manager.remove(key)
    except Exception:
        pass
