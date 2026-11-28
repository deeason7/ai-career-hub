"""Model packaging, inference readiness and degraded-score regression tests."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services import ats_scorer as scorer


@pytest.fixture
def model_constructor(monkeypatch):
    constructor = Mock()
    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=constructor)
    )
    scorer._get_model.cache_clear()
    yield constructor
    scorer._get_model.cache_clear()


def test_bundled_model_loads_offline_and_is_shared(monkeypatch, model_constructor):
    monkeypatch.setenv("ATS_MODEL_PATH", "/app/models/all-MiniLM-L6-v2")
    first = scorer._get_model()
    assert scorer._get_model() is first
    model_constructor.assert_called_once_with("/app/models/all-MiniLM-L6-v2", local_files_only=True)


def test_local_development_uses_the_model_cache(monkeypatch, model_constructor):
    monkeypatch.delenv("ATS_MODEL_PATH", raising=False)
    scorer._get_model()
    model_constructor.assert_called_once_with(scorer.MODEL_NAME)


def test_broken_bundle_does_not_fall_back_to_a_download(monkeypatch, model_constructor):
    monkeypatch.setenv("ATS_MODEL_PATH", "/missing/model")
    model_constructor.side_effect = OSError("missing weights")
    assert scorer.semantic_healthcheck()["status"] == "down"
    model_constructor.assert_called_once_with("/missing/model", local_files_only=True)


def test_semantic_probe_exercises_inference(monkeypatch):
    model = Mock()
    model.encode.return_value = [[1.0] * 384]
    monkeypatch.setattr(scorer, "_get_model", lambda: model)
    assert scorer.semantic_healthcheck() == {
        "status": "ok",
        "model": scorer.MODEL_NAME,
        "detail": None,
    }
    model.encode.assert_called_once()


@pytest.mark.parametrize(
    "embedding", [[], [1.0], [0.0] * 384, [float("nan")] * 384, [float("inf")] * 384]
)
def test_semantic_probe_rejects_unusable_embeddings(monkeypatch, embedding):
    model = Mock()
    model.encode.return_value = [embedding]
    monkeypatch.setattr(scorer, "_get_model", lambda: model)
    assert scorer.semantic_healthcheck()["status"] == "down"


def test_semantic_probe_does_not_expose_exception_contents(monkeypatch):
    monkeypatch.setattr(scorer, "_get_model", Mock(side_effect=OSError("private runtime path")))
    state = scorer.semantic_healthcheck()
    assert state["detail"] == "OSError"
    assert "private" not in str(state)


def test_zero_similarity_retains_the_semantic_weight(monkeypatch):
    monkeypatch.setattr(scorer, "_score_semantic", lambda *_: (0.0, {}))
    result = scorer.calculate_ats_score("Skills: Python. Experience: APIs.", "Python APIs")
    assert result.breakdown["semantic_weight"] == 0.5
    assert result.breakdown["keyword_weight"] == 0.3
    assert result.score == round(result.keyword_score * 0.3 + result.structure_score * 0.2, 1)


def test_inference_failure_uses_the_degraded_weights(monkeypatch):
    monkeypatch.setattr(scorer, "_score_semantic", Mock(side_effect=RuntimeError("model failed")))
    result = scorer.calculate_ats_score("Skills: Python. Experience: APIs.", "Python APIs")
    assert result.breakdown["semantic_weight"] == 0.0
    assert result.breakdown["keyword_weight"] == 0.8
    assert result.score == round(result.keyword_score * 0.8 + result.structure_score * 0.2, 1)
