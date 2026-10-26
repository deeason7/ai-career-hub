"""Read-only readiness checks for the API and deployed Streamlit application."""

import argparse
import http.cookiejar
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request


def dependency_problems(body: object) -> list[str]:
    if not isinstance(body, dict):
        return ["API health response is not an object"]
    problems = []
    if body.get("api") != "ok":
        problems.append("API is not ready")
    for name in ("db", "redis", "vector", "semantic"):
        value = body.get(name)
        state = value.get("status") if isinstance(value, dict) else value
        allowed = ("ok", "disabled") if name == "redis" else ("ok",)
        if state not in allowed:
            problems.append(f"{name}: {state or 'missing health signal'}")
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
        return [f"Streamlit is not running (status={status!r})"]
    return []


def get(opener: urllib.request.OpenerDirector, url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "CareerHub-Readiness/1.0"})
    with opener.open(request, timeout=60) as response:
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
        return response.read(1024 * 1024)


def probe(api_base: str | None, frontend_url: str | None, expected_version: str | None) -> dict:
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    result = {"ok": True, "checks": {}}
    for name, base in (("api", api_base), ("frontend", frontend_url)):
        if not base:
            continue
        try:
            if name == "api":
                body = json.loads(get(opener, f"{base.rstrip('/')}/health/warm"))
                problems = dependency_problems(body)
                if expected_version:
                    metadata = json.loads(get(opener, base))
                    version = metadata.get("version") if isinstance(metadata, dict) else None
                    if version != expected_version:
                        problems.append(f"version: expected {expected_version}, got {version}")
            elif urllib.parse.urlparse(base).hostname.endswith(".streamlit.app"):
                # Cookie handling follows the public viewer's login redirects.
                body = json.loads(get(opener, f"{base.rstrip('/')}/api/v2/app/status"))
                problems = streamlit_problems(body)
                if not problems:
                    body = get(opener, f"{base.rstrip('/')}/~/+/_stcore/health")
                    if body.strip() != b"ok":
                        problems.append("Streamlit runtime health did not return ok")
            else:
                body = get(opener, f"{base.rstrip('/')}/_stcore/health")
                problems = [] if body.strip() == b"ok" else ["Streamlit health did not return ok"]
        except (urllib.error.URLError, ValueError, TimeoutError, OSError) as exc:
            # Provider redirects may contain session payloads; never echo URLs.
            problems = [f"{name} probe failed: {type(exc).__name__}"]
        result["checks"][name] = {"ok": not problems, "problems": problems}
        result["ok"] = result["ok"] and not problems
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base")
    parser.add_argument("--frontend-url")
    parser.add_argument("--expected-version")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=30)
    args = parser.parse_args()
    if not (args.api_base or args.frontend_url):
        parser.error("provide --api-base and/or --frontend-url")
    if args.attempts < 1 or args.retry_delay < 0:
        parser.error("attempts must be positive and retry-delay must be nonnegative")
    for base in (args.api_base, args.frontend_url):
        if base:
            parsed = urllib.parse.urlparse(base)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                parser.error("probe URLs must be absolute HTTP(S) URLs")
    for attempt in range(1, args.attempts + 1):
        result = probe(args.api_base, args.frontend_url, args.expected_version)
        print(json.dumps({"attempt": attempt, **result}), flush=True)
        if result["ok"]:
            return 0
        if attempt < args.attempts:
            time.sleep(args.retry_delay)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
