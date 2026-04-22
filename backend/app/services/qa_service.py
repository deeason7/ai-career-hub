"""AI-as-a-Judge QA Service.

After cover letter generation, this service runs a second LLM pass with a
"Reviewer" persona that scores the letter against the original resume for
honesty (are claims traceable?) and tone (professional, not sycophantic?).
"""

import logging

from app.services.llm_client import call_structured
from app.services.llm_schemas import QAVerdict

logger = logging.getLogger(__name__)

# Letters scoring below this on honesty get flagged for the user.
HALLUCINATION_THRESHOLD = 6

# Max auto-regeneration attempts when honesty score is below threshold.
MAX_QA_RETRIES = 2

_REVIEWER_SYSTEM_PROMPT = """\
You are a rigorous QA reviewer for cover letters. Your job is to compare
a generated cover letter against the candidate's actual resume and score it.

SCORING CRITERIA:

honesty_score (1-10):
  10 = Every claim in the letter is directly traceable to the resume
   7 = Minor embellishments but no fabricated claims
   4 = Some claims are not in the resume
   1 = Most claims are fabricated

tone_score (1-10):
  10 = Professional, confident, natural
   7 = Slightly formal but appropriate
   4 = Either too casual or too sycophantic
   1 = Robotic, generic, or excessively flattering

flags: List EVERY specific claim in the cover letter that is NOT
       supported by the resume. Be precise (e.g. "claims 8 years of
       experience but resume shows 4 years").

reasoning: Brief justification for your scores (2-3 sentences).

Be strict. Err on the side of flagging rather than missing fabrications."""

_REVIEWER_USER_TEMPLATE = """\
CANDIDATE RESUME:
{resume_text}

GENERATED COVER LETTER:
{cover_letter}

JOB DESCRIPTION:
{job_description}

Score this cover letter against the resume. \
Respond with JSON: {{"honesty_score": 8, "tone_score": 7, "flags": [], \
"reasoning": "The letter accurately reflects..."}}"""


def review_cover_letter(
    cover_letter: str,
    resume_text: str,
    job_description: str,
) -> QAVerdict:
    """Run the AI reviewer on a generated cover letter.

    Args:
        cover_letter: The generated cover letter text to review.
        resume_text: The original resume text (source of truth).
        job_description: The JD the letter was tailored to.

    Returns:
        QAVerdict with honesty/tone scores, flags, and reasoning.

    Raises:
        ValidationError: If the reviewer LLM can't produce valid structured output.
    """
    user_prompt = _REVIEWER_USER_TEMPLATE.format(
        resume_text=resume_text[:4000],
        cover_letter=cover_letter,
        job_description=job_description[:2000],
    )

    verdict = call_structured(
        response_model=QAVerdict,
        system_prompt=_REVIEWER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.1,  # Low temp for consistent, deterministic scoring
        max_retries=2,
    )

    logger.info(
        "QA verdict: honesty=%d, tone=%d, flags=%d",
        verdict.honesty_score,
        verdict.tone_score,
        len(verdict.flags),
    )
    return verdict


def passes_qa(verdict: QAVerdict) -> bool:
    """Check if a cover letter passes the honesty threshold."""
    return verdict.honesty_score >= HALLUCINATION_THRESHOLD
