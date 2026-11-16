"""Run the authenticated document cleanup once and report a redacted result."""

import argparse
import http.client
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request

MAX_RESPONSE_BYTES = 64 * 1024
COUNT_FIELDS = ("deleted_resumes", "deleted_cover_letters", "reaped_stuck_cover_letters")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # The admin header belongs to this endpoint, including on POST redirects.
        return None


def valid_api_base(base: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(base)
        _ = parsed.port
        return (
            parsed.scheme in ("http", "https")
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and not any(ord(character) <= 32 for character in base)
        )
    except ValueError:
        return False


def cleanup(api_base: str, admin_secret: str, timeout: float = 60) -> dict:
    """Send one cleanup request; an uncertain write must not be retried automatically."""
    if not valid_api_base(api_base):
        return {"ok": False, "error": "Invalid API base URL"}
    if not admin_secret.strip() or any(ord(character) < 32 for character in admin_secret):
        return {"ok": False, "error": "ADMIN_SECRET is missing or invalid"}
    if not math.isfinite(timeout) or not 0 < timeout <= 60:
        return {"ok": False, "error": "Timeout must be greater than zero and at most 60 seconds"}

    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/api/v1/admin/lifecycle/run",
        data=b"",
        method="POST",
        headers={"X-Admin-Secret": admin_secret, "User-Agent": "CareerHub-Lifecycle/1.0"},
    )
    opener = urllib.request.build_opener(NoRedirect())
    status = None
    try:
        with opener.open(request, timeout=timeout) as response:
            status = response.status
            if status != 200:
                return {"ok": False, "http_status": status, "error": "Unexpected HTTP status"}
            body = response.read(MAX_RESPONSE_BYTES + 1)
            length = response.headers.get("Content-Length")
            if length is not None and int(length) != len(body):
                return {"ok": False, "http_status": status, "error": "Incomplete response"}
        if len(body) > MAX_RESPONSE_BYTES:
            return {"ok": False, "http_status": status, "error": "Response is too large"}
        payload = json.loads(body)
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            return {"ok": False, "http_status": status, "error": "Invalid cleanup response"}
        counts = {field: payload.get(field) for field in COUNT_FIELDS}
        if any(type(value) is not int or value < 0 for value in counts.values()):
            return {"ok": False, "http_status": status, "error": "Invalid cleanup counts"}
        return {"ok": True, "http_status": status, "counts": counts}
    except urllib.error.HTTPError as exc:
        result = {"ok": False, "http_status": exc.code, "error": "HTTPError"}
        try:
            body = exc.read(MAX_RESPONSE_BYTES + 1)
            payload = json.loads(body) if len(body) <= MAX_RESPONSE_BYTES else None
            detail = payload.get("detail") if isinstance(payload, dict) else None
            if isinstance(detail, str):
                match = re.fullmatch(
                    r"Lifecycle cleanup failed: ([A-Za-z_][A-Za-z_0-9]{0,99})", detail
                )
                if match:
                    result["error_class"] = match.group(1)
        except (ValueError, OSError, http.client.HTTPException):
            pass
        finally:
            exc.close()
        return result
    except (urllib.error.URLError, ValueError, OSError, http.client.HTTPException) as exc:
        return {"ok": False, "http_status": status, "error": type(exc).__name__}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args(argv)
    result = cleanup(args.api_base, os.environ.get("ADMIN_SECRET", ""), args.timeout)
    print(json.dumps(result), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
