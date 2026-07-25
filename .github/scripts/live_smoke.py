"""End-to-end probe of a live deployment: auth, upload, ATS score, cover letter, QA."""

import argparse
import sys
import time
import uuid

import requests

DEFAULT_BASE = "https://deeason-careerhub.hf.space"

RESUME = """Jordan Reyes
Austin, TX | jordan.reyes@example.com | (512) 555-0193

SUMMARY
Backend engineer with four years building Python web services and data pipelines.

EXPERIENCE
Software Engineer, Larkspur Analytics - 2022 to present
- Built FastAPI microservices backed by PostgreSQL and Redis serving 40k daily requests
- Cut p95 latency 38% by moving report generation onto async workers with Redis caching
- Containerized the stack with Docker Compose and wired GitHub Actions CI around pytest

Junior Developer, Bellwether Systems - 2020 to 2022
- Maintained Django REST endpoints and wrote ETL jobs in Python and SQL
- Added integration tests that caught three production regressions in the first quarter

SKILLS
Python, FastAPI, Django, PostgreSQL, Redis, Docker, GitHub Actions, pytest, SQL, REST APIs

EDUCATION
B.S. Computer Science, Texas State University, 2020
"""

JOB_DESCRIPTION = """Backend Engineer

We are hiring a backend engineer to build and operate Python services.

Responsibilities:
- Design REST APIs with FastAPI and keep them fast and reliable
- Model data in PostgreSQL and manage caching with Redis
- Ship through Docker and CI/CD pipelines with solid pytest coverage

Requirements:
- 3+ years of Python backend experience
- Production experience with FastAPI or Django, PostgreSQL, and Docker
- Comfort owning services end to end, from schema to deploy
"""


def fail(step: str, detail: str = "") -> None:
    print(f"\nFAIL at {step}: {str(detail)[:400]}")
    sys.exit(1)


def expect(resp: requests.Response, step: str, codes: tuple[int, ...]) -> dict:
    if resp.status_code not in codes:
        fail(step, f"HTTP {resp.status_code} — {resp.text[:300]}")
    try:
        return resp.json()
    except ValueError:
        fail(step, f"non-JSON body — {resp.text[:200]}")


def wait_for_health(base: str) -> None:
    # First hit doubles as the wake-up call on a suspended free tier; only give
    # up if the stack stays unhealthy across three spaced attempts.
    for attempt in range(1, 4):
        if attempt > 1:
            time.sleep(30)
        try:
            resp = requests.get(f"{base}/health/warm", timeout=60)
            body = resp.json()
            if resp.status_code == 200 and body.get("api") == "ok":
                print(f"health: {body}")
                return
            print(f"attempt {attempt}: unhealthy — {str(body)[:200]}")
        except (requests.RequestException, ValueError) as exc:
            print(f"attempt {attempt}: {type(exc).__name__}")
    fail("health gate", "stack stayed unhealthy across 3 attempts")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--letter-timeout", type=int, default=300)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    api = f"{base}/api/v1"
    started = time.monotonic()

    print(f"probing {base}")
    wait_for_health(base)

    tag = uuid.uuid4().hex[:10]
    email = f"smoke-{tag}@example.com"
    password = f"Probe-{uuid.uuid4().hex[:12]}9"  # 12+ chars, digit, uppercase, symbol

    resp = requests.post(
        f"{api}/auth/register",
        json={"email": email, "password": password, "full_name": "Smoke Probe"},
        timeout=60,
    )
    expect(resp, "register", (200, 201))
    print(f"registered {email}")

    resp = requests.post(
        f"{api}/auth/login",
        data={"username": email, "password": password},
        timeout=60,
    )
    token = expect(resp, "login", (200,)).get("access_token")
    if not token:
        fail("login", "no access_token in response")
    auth = {"Authorization": f"Bearer {token}"}
    print("logged in")

    resp = requests.post(
        f"{api}/resumes/upload",
        data={"name": "Smoke Probe Resume"},
        files={"file": ("resume.txt", RESUME.encode(), "text/plain")},
        headers=auth,
        timeout=240,
    )
    resume = expect(resp, "resume upload", (200, 201))
    resume_id = resume.get("id")
    if not resume_id:
        fail("resume upload", f"no id in response — {str(resume)[:200]}")
    print(f"resume uploaded ({resume_id})")

    resp = requests.post(
        f"{api}/ai/ats-score",
        json={"resume_id": resume_id, "job_description": JOB_DESCRIPTION},
        headers=auth,
        timeout=120,
    )
    ats = expect(resp, "ats score", (200,))
    score = ats.get("score")
    if not isinstance(score, (int, float)) or not 0 <= score <= 100:
        fail("ats score", f"implausible score — {str(ats)[:200]}")
    print(
        f"ats score {score} (semantic {ats.get('semantic_score')}, "
        f"keyword {ats.get('keyword_score')}, structure {ats.get('structure_score')})"
    )
    if not ats.get("semantic_score"):
        # The scorer renormalizes when the embedding model is unavailable, so a
        # zero here means degraded scoring that the total quietly hides.
        print("warning: semantic component is 0 — embedding model likely failed to load")

    resp = requests.post(
        f"{api}/cover-letters/generate",
        json={"resume_id": resume_id, "job_description": JOB_DESCRIPTION},
        headers=auth,
        timeout=60,
    )
    letter = expect(resp, "generate", (202,))
    task_id, letter_id = letter.get("task_id"), letter.get("id")
    if not task_id:
        fail("generate", f"202 without a task_id — {str(letter)[:200]}")
    print(f"generation accepted (task {task_id})")

    # A failed letter keeps polling as PENDING/null by design — completion is a
    # non-null result, and the hard timeout below is the failure detector.
    deadline = time.monotonic() + args.letter_timeout
    body = {}
    while time.monotonic() < deadline:
        time.sleep(5)
        resp = requests.get(f"{api}/cover-letters/task/{task_id}", headers=auth, timeout=60)
        body = expect(resp, "poll", (200,))
        if body.get("result"):
            break
    else:
        resp = requests.get(f"{api}/cover-letters/{letter_id}", headers=auth, timeout=60)
        fail("letter wait", f"timeout {args.letter_timeout}s — letter says {resp.text[:250]}")

    text = body["result"]
    if len(text) < 200:
        fail("letter content", f"suspiciously short ({len(text)} chars)")
    qa = body.get("qa")
    if qa:
        print(
            f"qa honesty {qa.get('honesty_score')}/10, tone {qa.get('tone_score')}/10, "
            f"flags {qa.get('flags')}, passed {qa.get('passed')}"
        )
    else:
        print("warning: letter completed without QA scores")

    print(
        f"\nPASS — {len(text)}-char letter in {time.monotonic() - started:.0f}s total; "
        f"probe rows expire via the 15-day lifecycle purge"
    )


if __name__ == "__main__":
    main()
