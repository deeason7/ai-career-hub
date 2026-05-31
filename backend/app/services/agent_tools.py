"""Tool wrappers for the agentic workflow.

Each function adapts an existing service into a LangGraph node signature:
accepts AgentState, returns a partial state update dict.
"""

import logging
import time

logger = logging.getLogger(__name__)


def tool_scrape_job(state: dict) -> dict:
    """Fetch and parse a job description from a URL."""
    import asyncio

    from app.services.job_scraper import JobFetchError, fetch_job_description

    url = state["job_url"]
    start = time.perf_counter()

    try:
        result = asyncio.get_event_loop().run_until_complete(fetch_job_description(url))
        elapsed = int((time.perf_counter() - start) * 1000)
        jd = result["job_description"]
        logger.info("scrape_job: fetched %d chars in %dms", len(jd), elapsed)
        return {
            "job_description": jd,
            "steps_completed": [
                {
                    "name": "scrape_job",
                    "status": "success",
                    "duration_ms": elapsed,
                    "detail": f"Fetched {len(jd)} chars (source: {result['source']})",
                }
            ],
        }
    except JobFetchError as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.warning("scrape_job failed: %s", exc)
        return {
            "errors": [f"scrape_job: {exc}"],
            "steps_completed": [
                {
                    "name": "scrape_job",
                    "status": "failed",
                    "duration_ms": elapsed,
                    "detail": str(exc),
                }
            ],
        }


def tool_extract_metadata(state: dict) -> dict:
    """Extract company name, role, and skills from the job description."""
    from app.services.job_tracker_service import extract_job_metadata

    if not state.get("job_description"):
        return {
            "errors": ["extract_metadata: no job description available"],
            "steps_completed": [
                {
                    "name": "extract_metadata",
                    "status": "skipped",
                    "duration_ms": 0,
                    "detail": "No JD",
                }
            ],
        }

    start = time.perf_counter()
    try:
        metadata = extract_job_metadata(state["job_description"])
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.info(
            "extract_metadata: %s @ %s (%dms)", metadata["role"], metadata["company"], elapsed
        )
        return {
            "job_metadata": metadata,
            "steps_completed": [
                {
                    "name": "extract_metadata",
                    "status": "success",
                    "duration_ms": elapsed,
                    "detail": f"{metadata['role']} @ {metadata['company']}",
                }
            ],
        }
    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.warning("extract_metadata failed: %s", exc)
        return {
            "job_metadata": {"company": "Unknown Company", "role": "Unknown Role"},
            "errors": [f"extract_metadata: {exc}"],
            "steps_completed": [
                {
                    "name": "extract_metadata",
                    "status": "failed",
                    "duration_ms": elapsed,
                    "detail": str(exc),
                }
            ],
        }


def tool_search_company(state: dict) -> dict:
    """Search the web for company information using DuckDuckGo."""
    company = (state.get("job_metadata") or {}).get("company", "")
    role = (state.get("job_metadata") or {}).get("role", "")

    if not company or company == "Unknown Company":
        return {
            "steps_completed": [
                {
                    "name": "search_company",
                    "status": "skipped",
                    "duration_ms": 0,
                    "detail": "No company identified",
                }
            ],
        }

    start = time.perf_counter()
    try:
        from ddgs import DDGS

        query = f"{company} {role} company culture engineering team"
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=5)

        snippets = [f"- {r['title']}: {r['body']}" for r in results if r.get("body")]
        company_intel = "\n".join(snippets[:5])
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.info(
            "search_company: found %d results for '%s' in %dms", len(snippets), company, elapsed
        )
        return {
            "company_research": company_intel,
            "steps_completed": [
                {
                    "name": "search_company",
                    "status": "success",
                    "duration_ms": elapsed,
                    "detail": f"Found {len(snippets)} results for {company}",
                }
            ],
        }
    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.warning("search_company failed: %s", exc)
        return {
            "company_research": "",
            "errors": [f"search_company: {exc}"],
            "steps_completed": [
                {
                    "name": "search_company",
                    "status": "failed",
                    "duration_ms": elapsed,
                    "detail": str(exc),
                }
            ],
        }


def tool_score_ats(state: dict) -> dict:
    """Run ATS scoring: semantic + keyword + structure analysis."""
    from app.services.ats_scorer import calculate_ats_score

    if not state.get("job_description") or not state.get("resume_text"):
        return {
            "errors": ["score_ats: missing resume or JD"],
            "steps_completed": [
                {
                    "name": "score_ats",
                    "status": "skipped",
                    "duration_ms": 0,
                    "detail": "Missing input",
                }
            ],
        }

    start = time.perf_counter()
    try:
        result = calculate_ats_score(state["resume_text"], state["job_description"])
        elapsed = int((time.perf_counter() - start) * 1000)
        ats_dict = {
            "score": result.score,
            "semantic_score": result.semantic_score,
            "keyword_score": result.keyword_score,
            "structure_score": result.structure_score,
            "matched_keywords": result.matched_keywords[:15],
            "missing_keywords": result.missing_keywords[:10],
            "recommendations": result.recommendations,
        }
        logger.info(
            "score_ats: %.1f (semantic=%.1f, kw=%.1f) in %dms",
            result.score,
            result.semantic_score,
            result.keyword_score,
            elapsed,
        )
        return {
            "ats_result": ats_dict,
            "steps_completed": [
                {
                    "name": "score_ats",
                    "status": "success",
                    "duration_ms": elapsed,
                    "detail": f"ATS score: {result.score}/100",
                }
            ],
        }
    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.warning("score_ats failed: %s", exc)
        return {
            "errors": [f"score_ats: {exc}"],
            "steps_completed": [
                {
                    "name": "score_ats",
                    "status": "failed",
                    "duration_ms": elapsed,
                    "detail": str(exc),
                }
            ],
        }


def tool_analyze_gaps(state: dict) -> dict:
    """Identify missing skills and generate learning recommendations."""
    from app.services.cover_letter import generate_skill_gap_analysis

    if not state.get("job_description") or not state.get("resume_text"):
        return {
            "errors": ["analyze_gaps: missing resume or JD"],
            "steps_completed": [
                {
                    "name": "analyze_gaps",
                    "status": "skipped",
                    "duration_ms": 0,
                    "detail": "Missing input",
                }
            ],
        }

    start = time.perf_counter()
    try:
        result = generate_skill_gap_analysis(state["resume_text"], state["job_description"])
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.info(
            "analyze_gaps: %d missing skills in %dms",
            len(result.get("missing_skills", [])),
            elapsed,
        )
        return {
            "skill_gap": result,
            "steps_completed": [
                {
                    "name": "analyze_gaps",
                    "status": "success",
                    "duration_ms": elapsed,
                    "detail": f"{len(result.get('priority_gaps', []))} priority gaps",
                }
            ],
        }
    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.warning("analyze_gaps failed: %s", exc)
        return {
            "errors": [f"analyze_gaps: {exc}"],
            "steps_completed": [
                {
                    "name": "analyze_gaps",
                    "status": "failed",
                    "duration_ms": elapsed,
                    "detail": str(exc),
                }
            ],
        }


def tool_write_cover_letter(state: dict) -> dict:
    """Generate a tailored cover letter grounded in resume facts."""
    from app.services.cover_letter import generate_cover_letter

    if not state.get("job_description") or not state.get("resume_text"):
        return {
            "errors": ["write_cover_letter: missing resume or JD"],
            "steps_completed": [
                {
                    "name": "write_cover_letter",
                    "status": "skipped",
                    "duration_ms": 0,
                    "detail": "Missing input",
                }
            ],
        }

    start = time.perf_counter()
    try:
        result = generate_cover_letter(state["resume_text"], state["job_description"])
        elapsed = int((time.perf_counter() - start) * 1000)
        letter = result.get("cover_letter", "")
        logger.info("write_cover_letter: %d chars in %dms", len(letter), elapsed)
        return {
            "cover_letter": result,
            "steps_completed": [
                {
                    "name": "write_cover_letter",
                    "status": "success",
                    "duration_ms": elapsed,
                    "detail": f"Generated {len(letter)} chars",
                }
            ],
        }
    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.warning("write_cover_letter failed: %s", exc)
        return {
            "errors": [f"write_cover_letter: {exc}"],
            "steps_completed": [
                {
                    "name": "write_cover_letter",
                    "status": "failed",
                    "duration_ms": elapsed,
                    "detail": str(exc),
                }
            ],
        }


def tool_generate_questions(state: dict) -> dict:
    """Generate role-specific interview questions."""
    from app.services.cover_letter import generate_interview_questions

    if not state.get("job_description") or not state.get("resume_text"):
        return {
            "errors": ["generate_questions: missing resume or JD"],
            "steps_completed": [
                {
                    "name": "generate_questions",
                    "status": "skipped",
                    "duration_ms": 0,
                    "detail": "Missing input",
                }
            ],
        }

    start = time.perf_counter()
    try:
        questions = generate_interview_questions(state["resume_text"], state["job_description"])
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.info("generate_questions: %d questions in %dms", len(questions), elapsed)
        return {
            "interview_questions": questions,
            "steps_completed": [
                {
                    "name": "generate_questions",
                    "status": "success",
                    "duration_ms": elapsed,
                    "detail": f"Generated {len(questions)} questions",
                }
            ],
        }
    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.warning("generate_questions failed: %s", exc)
        return {
            "errors": [f"generate_questions: {exc}"],
            "steps_completed": [
                {
                    "name": "generate_questions",
                    "status": "failed",
                    "duration_ms": elapsed,
                    "detail": str(exc),
                }
            ],
        }
