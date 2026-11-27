"""Read-only readiness checks for the API and deployed Streamlit application."""

import argparse
import http.client
import http.cookiejar
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request

MAX_BODY_BYTES = 1024 * 1024
MAX_REDIRECTS = 5
REQUEST_TIMEOUT = 30.0
LEGACY_SEMANTIC_VERSION = "4.4.3"


class ProbeError(ValueError):
    """A bounded diagnostic that never includes provider response content."""

    def __init__(self, reason: str, http_status: int | None = None):
        super().__init__(reason)
        self.http_status = http_status


class RedirectHandler(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS
    max_repeats = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        source = urllib.parse.urlsplit(req.full_url)
        target = urllib.parse.urlsplit(newurl)
        if target.scheme not in ("http", "https") or (
            source.scheme == "https" and target.scheme != "https"
        ):
            raise ProbeError("unsafe_redirect", code)
        if target.username or target.password:
            raise ProbeError("unsafe_redirect", code)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def build_opener(*, allow_redirects: bool = True) -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        RedirectHandler() if allow_redirects else NoRedirect(),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )


def dependency_problems(
    body: object, *, allow_missing_semantic: bool = False, require_redis: bool = False
) -> list[str]:
    if not isinstance(body, dict):
        return ["API health response is not an object"]
    problems = []
    if body.get("api") != "ok":
        problems.append("API is not ready")
    for name in ("db", "redis", "vector", "semantic"):
        if name == "semantic" and name not in body and allow_missing_semantic:
            continue
        value = body.get(name)
        state = value.get("status") if isinstance(value, dict) else value
        allowed = ("ok", "disabled") if name == "redis" and not require_redis else ("ok",)
        if state not in allowed:
            signal = state if state in ("down", "disabled") else "missing or invalid health signal"
            if value is None:
                signal = "missing health signal"
            problems.append(f"{name}: {signal}")
    return problems


def ats_problems(body: dict) -> list[str]:
    score = body.get("score")
    problems = []
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 100:
        problems.append("ATS score is outside 0–100")
    breakdown = body.get("breakdown")
    weight = breakdown.get("semantic_weight") if isinstance(breakdown, dict) else None
    if (
        isinstance(weight, bool)
        or not isinstance(weight, (int, float))
        or not math.isfinite(weight)
        or not 0 < weight <= 1
    ):
        problems.append("ATS semantic channel is unavailable or its weight is missing")
    return problems


def streamlit_problems(body: object) -> list[str]:
    if not isinstance(body, dict):
        return ["Streamlit runtime status is unavailable"]
    # Community Cloud serves HTTP 200 for the sleeping screen too. Its public
    # viewer status distinguishes RUNNING (5) from IS_SHUTDOWN (12).
    status = body.get("status")
    if status == 12:
        return ["Streamlit is asleep; open the app and select 'Yes, get this app back up!'"]
    if status != 5:
        return ["Streamlit is not running"]
    return []


def get(opener: urllib.request.OpenerDirector, url: str, timeout: float = REQUEST_TIMEOUT) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "CareerHub-Readiness/1.0"})
    status = None
    try:
        with opener.open(request, timeout=timeout) as response:
            status = response.status
            if status != 200:
                raise ProbeError("unexpected_http_status", status)
            body = response.read(MAX_BODY_BYTES + 1)
            if len(body) > MAX_BODY_BYTES:
                raise ProbeError("response_too_large", status)
            length = response.headers.get("Content-Length")
            if length is not None:
                try:
                    expected = int(length)
                except ValueError:
                    raise ProbeError("invalid_content_length", status) from None
                if expected != len(body):
                    raise ProbeError("incomplete_response", status)
            return body
    except urllib.error.HTTPError as exc:
        exc.close()
        raise ProbeError("HTTPError", exc.code) from None
    except ProbeError:
        raise
    except (urllib.error.URLError, ValueError, OSError, http.client.HTTPException) as exc:
        raise ProbeError(type(exc).__name__, status) from None


def probe(
    api_base: str | None,
    frontend_url: str | None,
    expected_version: str | None,
    *,
    allow_missing_semantic: bool = False,
    require_redis: bool = False,
    report_version: bool = False,
    request_timeout: float = REQUEST_TIMEOUT,
) -> dict:
    result = {"ok": True, "checks": {}}
    for name, base in (("api", api_base), ("frontend", frontend_url)):
        if not base:
            continue
        start = time.monotonic()
        opener = build_opener(allow_redirects=name == "frontend")
        warnings = []
        diagnostic = {}

        def read(url: str, opener=opener, diagnostic=diagnostic) -> bytes:
            body = get(opener, url, timeout=request_timeout)
            diagnostic["http_status"] = 200
            return body

        try:
            if name == "api":
                body = json.loads(read(f"{base.rstrip('/')}/health/warm"))
                problems = dependency_problems(
                    body, allow_missing_semantic=allow_missing_semantic, require_redis=require_redis
                )
                if isinstance(body, dict):
                    signals = {}
                    for dep in ("api", "db", "redis", "vector", "semantic"):
                        value = body.get(dep)
                        state = value.get("status") if isinstance(value, dict) else value
                        signals[dep] = (
                            state if state in ("ok", "disabled", "down") else "unverified"
                        )
                    diagnostic["dependencies"] = signals
                legacy_missing = (
                    allow_missing_semantic and isinstance(body, dict) and "semantic" not in body
                )
                if legacy_missing or expected_version or report_version:
                    metadata = json.loads(read(base))
                    version = metadata.get("version") if isinstance(metadata, dict) else None
                    if isinstance(version, str) and re.fullmatch(
                        r"[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}", version
                    ):
                        diagnostic["version"] = version
                    if legacy_missing and version == LEGACY_SEMANTIC_VERSION:
                        warnings.append("semantic readiness unverified: v4.4.3 has no signal")
                    elif legacy_missing:
                        problems.append("semantic: missing health signal outside legacy v4.4.3")
                    if expected_version and version != expected_version:
                        problems.append(f"version: expected {expected_version}, release mismatch")
                    if report_version and "version" not in diagnostic:
                        problems.append("API version is missing or invalid")
            elif urllib.parse.urlparse(base).hostname.endswith(".streamlit.app"):
                # Cookie handling follows the public viewer's login redirects.
                body = json.loads(read(f"{base.rstrip('/')}/api/v2/app/status"))
                problems = streamlit_problems(body)
                if not problems:
                    body = read(f"{base.rstrip('/')}/~/+/_stcore/health")
                    if body.strip() != b"ok":
                        problems.append("Streamlit runtime health did not return ok")
            else:
                body = read(f"{base.rstrip('/')}/_stcore/health")
                problems = [] if body.strip() == b"ok" else ["Streamlit health did not return ok"]
            diagnostic["http_status"] = 200
        except urllib.error.HTTPError as exc:
            diagnostic = {"http_status": exc.code, "error": "HTTPError"}
            problems = [f"{name} probe failed: HTTP {exc.code}"]
            exc.close()
        except ProbeError as exc:
            diagnostic = {"http_status": exc.http_status, "error": str(exc)}
            problems = [f"{name} probe failed: {exc}"]
        except (urllib.error.URLError, ValueError, OSError, http.client.HTTPException) as exc:
            # Provider redirects may contain session payloads; never echo URLs.
            diagnostic.update(error=type(exc).__name__)
            diagnostic.setdefault("http_status", None)
            problems = [f"{name} probe failed: {type(exc).__name__}"]
        stage = "dependencies" if name == "api" else "runtime"
        if not problems:
            stage = "ready"
        elif "error" in diagnostic:
            stage = "response"
        result["checks"][name] = {
            "ok": not problems,
            "problems": problems,
            "warnings": warnings,
            "stage": stage,
            "elapsed_ms": round((time.monotonic() - start) * 1000),
            **diagnostic,
        }
        result["ok"] = result["ok"] and not problems
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base")
    parser.add_argument("--frontend-url")
    parser.add_argument("--expected-version")
    parser.add_argument("--report-version", action="store_true")
    parser.add_argument("--require-redis", action="store_true")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=30)
    parser.add_argument("--request-timeout", type=float, default=REQUEST_TIMEOUT)
    parser.add_argument(
        "--allow-missing-semantic",
        action="store_true",
        help="keep-warm compatibility with v4.4.3; never use for release validation",
    )
    args = parser.parse_args()
    if not (args.api_base or args.frontend_url):
        parser.error("provide --api-base and/or --frontend-url")
    if args.attempts < 1 or not math.isfinite(args.retry_delay) or args.retry_delay < 0:
        parser.error("attempts must be positive and retry-delay must be nonnegative")
    if not math.isfinite(args.request_timeout) or args.request_timeout <= 0:
        parser.error("request-timeout must be finite and positive")
    if args.expected_version and args.allow_missing_semantic:
        parser.error("release validation requires the semantic health signal")
    for base in (args.api_base, args.frontend_url):
        if base:
            try:
                parsed = urllib.parse.urlparse(base)
                valid = (
                    parsed.scheme in ("http", "https")
                    and parsed.hostname
                    and not parsed.username
                    and not parsed.password
                    and not parsed.query
                    and not parsed.fragment
                    and not any(ord(character) <= 32 for character in base)
                )
                _ = parsed.port
            except ValueError:
                valid = False
            if not valid:
                parser.error(
                    "probe base must be an HTTP(S) URL without credentials, query or fragment"
                )
    checks = {}
    for attempt in range(1, args.attempts + 1):
        result = probe(
            args.api_base if not checks.get("api", {}).get("ok") else None,
            args.frontend_url if not checks.get("frontend", {}).get("ok") else None,
            args.expected_version,
            allow_missing_semantic=args.allow_missing_semantic,
            require_redis=args.require_redis,
            report_version=args.report_version,
            request_timeout=args.request_timeout,
        )
        checks.update(result["checks"])
        result = {"ok": all(check["ok"] for check in checks.values()), "checks": checks}
        print(json.dumps({"attempt": attempt, **result}), flush=True)
        if result["ok"]:
            return 0
        if attempt < args.attempts:
            time.sleep(args.retry_delay)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
