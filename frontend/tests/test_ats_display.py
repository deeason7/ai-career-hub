"""Scoring cards distinguish an unavailable model from a genuine zero match."""

from unittest.mock import MagicMock, patch

import pytest

from ui import render_ats_score


@pytest.mark.parametrize(
    ("weights", "expected", "unavailable"),
    [
        ((0.5, 0.3, 0.2), ("50% weight", "30% weight", "20% weight"), False),
        ((0.0, 0.8, 0.2), ("0% weight", "80% weight", "20% weight"), True),
    ],
)
def test_scorecard_uses_actual_weights(weights, expected, unavailable):
    ats = {
        "score": 62,
        "semantic_score": 0,
        "keyword_score": 70,
        "structure_score": 50,
        "breakdown": dict(
            zip(("semantic_weight", "keyword_weight", "structure_weight"), weights, strict=True)
        ),
    }

    with patch("ui.st.html") as html, patch("ui.st.warning") as warning:
        render_ats_score(ats)

    rendered = html.call_args.args[0]
    assert all(weight in rendered for weight in expected)
    assert ("Unavailable" in rendered) is unavailable
    assert warning.called is unavailable
    if unavailable:
        assert "keywords and resume structure only" in warning.call_args.args[0]
    else:
        assert "<b>0% · 50% weight</b>" in rendered


def test_legacy_result_does_not_invent_weights_or_an_outage():
    with (
        patch("ui.st.html") as html,
        patch("ui.st.warning") as warning,
        patch("ui.st.caption") as caption,
    ):
        render_ats_score({"score": 62, "semantic_score": 0})

    assert html.call_args.args[0].count("weight unavailable") == 3
    warning.assert_not_called()
    assert "Run the analysis again" in caption.call_args.args[0]


def test_both_analysis_pages_render_the_shared_scorecard(monkeypatch):
    import ui
    from views import agent, job_match

    streamlit = MagicMock()
    streamlit.tabs.side_effect = lambda labels: [MagicMock() for _ in labels]
    streamlit.columns.side_effect = lambda widths: [
        MagicMock() for _ in range(widths if isinstance(widths, int) else len(widths))
    ]
    streamlit.button.return_value = False
    for module in (ui, agent, job_match):
        monkeypatch.setattr(module, "st", streamlit)

    ats = {"score": 60, "breakdown": {"semantic_weight": 0}}
    with patch("views.job_match.render_ats_score") as card:
        job_match._render_analysis({"ats": ats})
    card.assert_called_once_with(ats)

    with patch("views.agent.render_ats_score") as card:
        agent._render_results({"full_results": {"ats_result": ats}})
    card.assert_called_once_with(ats)
