"""Tests for the agentic workflow graph and tool wrappers."""

import uuid
from unittest.mock import MagicMock, patch

# --- Tool wrapper tests ---
# All tools use lazy imports inside each function body, so we patch at the
# SOURCE module rather than at agent_tools (where the names don't exist as
# module-level attributes).


class TestToolScrapeJob:
    def test_success_returns_job_description(self):
        from app.services.agent_tools import tool_scrape_job

        mock_result = {
            "success": True,
            "job_description": "We are looking for a Python developer...",
            "source": "json_ld",
            "warning": None,
        }

        # tool_scrape_job runs the async fetch via asyncio.run(); patch it so the
        # test neither spins a real event loop nor hits the network.
        with patch("app.services.job_scraper.fetch_job_description", new=MagicMock()):
            with patch("asyncio.run", return_value=mock_result):
                result = tool_scrape_job({"job_url": "https://example.com/job/123"})

        assert result["job_description"] == "We are looking for a Python developer..."
        assert result["steps_completed"][0]["status"] == "success"
        assert result["steps_completed"][0]["name"] == "scrape_job"

    def test_failure_returns_error(self):
        from app.services.agent_tools import tool_scrape_job
        from app.services.job_scraper import JobFetchError

        with patch("app.services.job_scraper.fetch_job_description", new=MagicMock()):
            with patch("asyncio.run", side_effect=JobFetchError("Timed out")):
                result = tool_scrape_job({"job_url": "https://example.com/bad"})

        assert "job_description" not in result
        assert len(result["errors"]) == 1
        assert "Timed out" in result["errors"][0]
        assert result["steps_completed"][0]["status"] == "failed"


class TestGetResumeText:
    """Regression: analyze endpoint must read Resume.raw_text, not extracted_text."""

    def test_returns_resume_raw_text(self):
        from app.api.v1.endpoints import agent as agent_ep
        from app.models.resume import Resume

        rid, uid = uuid.uuid4(), uuid.uuid4()
        resume = Resume(
            id=rid,
            user_id=uid,
            name="SWE Resume",
            original_filename="resume.pdf",
            raw_text="Senior Python engineer with FastAPI and AWS experience.",
            is_active=True,
        )
        session = MagicMock()
        session.exec.return_value.first.return_value = resume
        session.__enter__.return_value = session
        session.__exit__.return_value = False

        with patch.object(agent_ep, "Session", return_value=session):
            text = agent_ep._get_resume_text(rid, uid)

        assert "Senior Python engineer" in text


class TestToolExtractMetadata:
    def test_success_extracts_company_and_role(self):
        from app.services.agent_tools import tool_extract_metadata

        mock_metadata = {"company": "Acme Corp", "role": "ML Engineer"}
        with patch(
            "app.services.job_tracker_service.extract_job_metadata",
            return_value=mock_metadata,
        ):
            result = tool_extract_metadata(
                {"job_description": "We need an ML engineer at Acme Corp..."}
            )

        assert result["job_metadata"]["company"] == "Acme Corp"
        assert result["job_metadata"]["role"] == "ML Engineer"
        assert result["steps_completed"][0]["status"] == "success"

    def test_skipped_when_no_jd(self):
        from app.services.agent_tools import tool_extract_metadata

        result = tool_extract_metadata({"job_description": None})
        assert result["steps_completed"][0]["status"] == "skipped"


class TestToolScoreAts:
    def test_success_returns_score(self):
        from app.services.agent_tools import tool_score_ats

        mock_result = MagicMock()
        mock_result.score = 75.5
        mock_result.semantic_score = 80.0
        mock_result.keyword_score = 65.0
        mock_result.structure_score = 85.0
        mock_result.matched_keywords = ["python", "fastapi"]
        mock_result.missing_keywords = ["kubernetes"]
        mock_result.recommendations = ["Add Docker experience"]

        with patch(
            "app.services.ats_scorer.calculate_ats_score",
            return_value=mock_result,
        ):
            result = tool_score_ats(
                {
                    "resume_text": "Python developer with FastAPI experience",
                    "job_description": "Looking for Python + K8s engineer",
                }
            )

        assert result["ats_result"]["score"] == 75.5
        assert result["steps_completed"][0]["status"] == "success"

    def test_skipped_when_missing_input(self):
        from app.services.agent_tools import tool_score_ats

        result = tool_score_ats({"resume_text": None, "job_description": None})
        assert result["steps_completed"][0]["status"] == "skipped"


class TestToolSearchCompany:
    def test_success_returns_research(self):
        from app.services.agent_tools import tool_search_company

        mock_results = [
            {"title": "Acme Corp", "body": "Leading tech company", "href": "https://example.com"},
        ]

        with patch("ddgs.DDGS") as MockDDGS:
            mock_ddgs = MagicMock()
            mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
            mock_ddgs.__exit__ = MagicMock(return_value=False)
            mock_ddgs.text.return_value = mock_results
            MockDDGS.return_value = mock_ddgs

            result = tool_search_company(
                {
                    "job_metadata": {"company": "Acme Corp", "role": "Engineer"},
                }
            )

        assert result["steps_completed"][0]["status"] == "success"
        assert "Acme Corp" in result["company_research"]

    def test_skipped_when_unknown_company(self):
        from app.services.agent_tools import tool_search_company

        result = tool_search_company(
            {
                "job_metadata": {"company": "Unknown Company", "role": "Engineer"},
            }
        )
        assert result["steps_completed"][0]["status"] == "skipped"


class TestToolWriteCoverLetter:
    def test_success_generates_letter(self):
        from app.services.agent_tools import tool_write_cover_letter

        mock_result = {"cover_letter": "Dear Hiring Manager...", "chunks_used": 1}
        with patch(
            "app.services.cover_letter.generate_cover_letter",
            return_value=mock_result,
        ):
            result = tool_write_cover_letter(
                {
                    "resume_text": "Experienced developer...",
                    "job_description": "Looking for a developer...",
                }
            )

        assert result["cover_letter"]["cover_letter"] == "Dear Hiring Manager..."
        assert result["steps_completed"][0]["status"] == "success"


class TestToolGenerateQuestions:
    def test_success_generates_questions(self):
        from app.services.agent_tools import tool_generate_questions

        mock_questions = ["Tell me about your Python experience", "Describe a difficult bug"]
        with patch(
            "app.services.cover_letter.generate_interview_questions",
            return_value=mock_questions,
        ):
            result = tool_generate_questions(
                {
                    "resume_text": "Python developer...",
                    "job_description": "Senior Python role...",
                }
            )

        assert result["interview_questions"] == mock_questions
        assert result["steps_completed"][0]["status"] == "success"


# --- Graph integration tests ---


class TestAgentGraph:
    def test_graph_compiles(self):
        from app.services.agent_graph import build_agent_graph

        graph = build_agent_graph()
        assert graph is not None

    def test_full_run_with_mocked_tools(self):
        from app.services.agent_graph import run_agent

        mock_jd = "We need a Python developer at TestCo for an ML Engineer role..."
        mock_scrape = {
            "job_description": mock_jd,
            "steps_completed": [
                {"name": "scrape_job", "status": "success", "duration_ms": 100, "detail": "ok"}
            ],
        }
        mock_extract = {
            "job_metadata": {"company": "TestCo", "role": "ML Engineer"},
            "steps_completed": [
                {
                    "name": "extract_metadata",
                    "status": "success",
                    "duration_ms": 50,
                    "detail": "ok",
                }
            ],
        }
        mock_search = {
            "company_research": "TestCo is a leading company",
            "steps_completed": [
                {
                    "name": "search_company",
                    "status": "success",
                    "duration_ms": 200,
                    "detail": "ok",
                }
            ],
        }
        mock_ats = {
            "ats_result": {"score": 80.0},
            "steps_completed": [
                {"name": "score_ats", "status": "success", "duration_ms": 300, "detail": "ok"}
            ],
        }
        mock_gaps = {
            "skill_gap": {"priority_gaps": ["kubernetes"]},
            "steps_completed": [
                {"name": "analyze_gaps", "status": "success", "duration_ms": 400, "detail": "ok"}
            ],
        }
        mock_cl = {
            "cover_letter": {"cover_letter": "Dear Hiring Manager..."},
            "steps_completed": [
                {
                    "name": "write_cover_letter",
                    "status": "success",
                    "duration_ms": 500,
                    "detail": "ok",
                }
            ],
        }
        mock_iq = {
            "interview_questions": ["Q1", "Q2"],
            "steps_completed": [
                {
                    "name": "generate_questions",
                    "status": "success",
                    "duration_ms": 200,
                    "detail": "ok",
                }
            ],
        }

        with (
            patch("app.services.agent_graph.tool_scrape_job", return_value=mock_scrape),
            patch("app.services.agent_graph.tool_extract_metadata", return_value=mock_extract),
            patch("app.services.agent_graph.tool_search_company", return_value=mock_search),
            patch("app.services.agent_graph.tool_score_ats", return_value=mock_ats),
            patch("app.services.agent_graph.tool_analyze_gaps", return_value=mock_gaps),
            patch("app.services.agent_graph.tool_write_cover_letter", return_value=mock_cl),
            patch("app.services.agent_graph.tool_generate_questions", return_value=mock_iq),
            patch("app.services.agent_graph._compiled_graph", None),
        ):
            result = run_agent(
                job_url="https://example.com/job/1",
                resume_text="Python developer with 5 years experience",
                user_id="test-user-id",
            )

        assert result["status"] == "completed"
        assert len(result["steps"]) == 7
        assert result["summary"]["company"] == "TestCo"
        assert result["summary"]["ats_score"] == 80.0
        assert result["errors"] == []
        assert result["total_duration_ms"] > 0

    def test_scrape_failure_ends_early(self):
        from app.services.agent_graph import run_agent

        mock_scrape = {
            "job_description": None,
            "errors": ["scrape_job: timed out"],
            "steps_completed": [
                {
                    "name": "scrape_job",
                    "status": "failed",
                    "duration_ms": 100,
                    "detail": "timed out",
                }
            ],
        }

        with (
            patch("app.services.agent_graph.tool_scrape_job", return_value=mock_scrape),
            patch("app.services.agent_graph._compiled_graph", None),
        ):
            result = run_agent(
                job_url="https://example.com/bad",
                resume_text="Some resume",
                user_id="test-user-id",
            )

        assert result["status"] == "failed"
        assert len(result["steps"]) == 1
        assert result["steps"][0]["name"] == "scrape_job"
        assert len(result["errors"]) == 1
