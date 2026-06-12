"""LangGraph state graph for the agentic job application workflow.

Orchestrates a multi-step pipeline: scrape → extract → research → score → gap analysis
→ cover letter → interview prep. Each step is a tool node that updates shared state.
The graph handles partial failures gracefully — a failed step is logged and skipped
without aborting the entire workflow.
"""

import logging
import operator
import time
from collections.abc import Callable
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph

from app.services.agent_tools import (
    tool_analyze_gaps,
    tool_extract_metadata,
    tool_generate_questions,
    tool_score_ats,
    tool_scrape_job,
    tool_search_company,
    tool_write_cover_letter,
)

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    """Typed state schema for the agentic workflow.

    `steps_completed` and `errors` use the `add` reducer so each node appends
    rather than overwrites — the full execution trace accumulates automatically.
    """

    job_url: str
    user_id: str
    resume_text: str
    job_description: str | None
    job_metadata: dict | None
    company_research: str | None
    ats_result: dict | None
    skill_gap: dict | None
    cover_letter: dict | None
    interview_questions: list[str] | None
    steps_completed: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]


def _should_continue_after_scrape(state: AgentState) -> str:
    """Route after scrape: continue if JD was fetched, otherwise end early."""
    if state.get("job_description"):
        return "extract_metadata"
    return END


def build_agent_graph() -> StateGraph:
    """Construct and compile the agentic workflow graph.

    Graph topology:
        START → scrape_job → [if JD exists] → extract_metadata → search_company
              → score_ats → analyze_gaps → write_cover_letter
              → generate_questions → END

    If scraping fails, the graph ends early with the error recorded in state.
    All other node failures are captured in state.errors and execution continues.
    """
    graph = StateGraph(AgentState)

    graph.add_node("scrape_job", tool_scrape_job)
    graph.add_node("extract_metadata", tool_extract_metadata)
    graph.add_node("search_company", tool_search_company)
    graph.add_node("score_ats", tool_score_ats)
    graph.add_node("analyze_gaps", tool_analyze_gaps)
    graph.add_node("write_cover_letter", tool_write_cover_letter)
    graph.add_node("generate_questions", tool_generate_questions)

    graph.set_entry_point("scrape_job")

    graph.add_conditional_edges(
        "scrape_job",
        _should_continue_after_scrape,
        {"extract_metadata": "extract_metadata", END: END},
    )
    graph.add_edge("extract_metadata", "search_company")
    graph.add_edge("search_company", "score_ats")
    graph.add_edge("score_ats", "analyze_gaps")
    graph.add_edge("analyze_gaps", "write_cover_letter")
    graph.add_edge("write_cover_letter", "generate_questions")
    graph.add_edge("generate_questions", END)

    return graph.compile()


# Singleton compiled graph — built once on first import.
_compiled_graph = None


def get_agent_graph():
    """Return the compiled agent graph (singleton)."""
    global _compiled_graph  # noqa: PLW0603
    if _compiled_graph is None:
        _compiled_graph = build_agent_graph()
        logger.info("Agent graph compiled")
    return _compiled_graph


def run_agent(
    job_url: str,
    resume_text: str,
    user_id: str,
    on_step: Callable[[dict], None] | None = None,
) -> dict:
    """Execute the full agentic workflow and return the final state.

    `on_step`, when given, is called with the accumulated state after every
    node — progress reporting hooks in here without touching the tools.

    Returns a dict with:
        status: "completed" | "partial" | "failed"
        steps: list of step execution records
        summary: aggregated results
        errors: list of error messages
        total_duration_ms: total wall-clock time
    """
    graph = get_agent_graph()

    initial_state: AgentState = {
        "job_url": job_url,
        "user_id": user_id,
        "resume_text": resume_text,
        "job_description": None,
        "job_metadata": None,
        "company_research": None,
        "ats_result": None,
        "skill_gap": None,
        "cover_letter": None,
        "interview_questions": None,
        "steps_completed": [],
        "errors": [],
    }

    start = time.perf_counter()
    # Stream full state values instead of invoke(): same final state, but each
    # completed node yields once, which is what makes live progress possible.
    final_state: dict = dict(initial_state)
    for state in graph.stream(initial_state, stream_mode="values"):
        final_state = state
        if on_step is not None:
            try:
                on_step(state)
            except Exception as exc:
                logger.warning("agent progress callback failed (run continues): %s", exc)
    total_ms = int((time.perf_counter() - start) * 1000)

    steps = final_state.get("steps_completed", [])
    errors = final_state.get("errors", [])
    succeeded = sum(1 for s in steps if s["status"] == "success")
    total_steps = len(steps)

    if succeeded == 0:
        status = "failed"
    elif errors:
        status = "partial"
    else:
        status = "completed"

    summary = {
        "company": (final_state.get("job_metadata") or {}).get("company"),
        "role": (final_state.get("job_metadata") or {}).get("role"),
        "ats_score": (final_state.get("ats_result") or {}).get("score"),
        "cover_letter_preview": (final_state.get("cover_letter") or {}).get("cover_letter", "")[
            :200
        ],
        "skill_gaps": (final_state.get("skill_gap") or {}).get("priority_gaps", []),
        "interview_question_count": len(final_state.get("interview_questions") or []),
        "company_research_available": bool(final_state.get("company_research")),
    }

    logger.info(
        "Agent completed: status=%s, steps=%d/%d succeeded, %dms total",
        status,
        succeeded,
        total_steps,
        total_ms,
    )

    return {
        "status": status,
        "steps": steps,
        "summary": summary,
        "full_results": {
            "job_description": final_state.get("job_description"),
            "job_metadata": final_state.get("job_metadata"),
            "company_research": final_state.get("company_research"),
            "ats_result": final_state.get("ats_result"),
            "skill_gap": final_state.get("skill_gap"),
            "cover_letter": final_state.get("cover_letter"),
            "interview_questions": final_state.get("interview_questions"),
        },
        "errors": errors,
        "total_duration_ms": total_ms,
    }
