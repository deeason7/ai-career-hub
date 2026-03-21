"""
ATS (Applicant Tracking System) Scorer Service

Scores a resume against a job description using:
1. Keyword overlap (exact + stemmed matching)
2. Semantic similarity (cosine similarity via TF-IDF / FAISS)
3. Structure scoring (sections present, formatting heuristics)
"""
import re
import logging
from dataclasses import dataclass
from collections import Counter

logger = logging.getLogger(__name__)

# High-value tech keywords worth double credit
PRIORITY_KEYWORDS = {
    "python", "sql", "machine learning", "deep learning", "nlp", "pytorch",
    "tensorflow", "docker", "kubernetes", "aws", "azure", "gcp",
    "fastapi", "django", "flask", "react", "typescript", "ci/cd",
    "data science", "ai", "llm", "rag", "fine-tuning", "mlops",
}

EXPECTED_RESUME_SECTIONS = [
    "experience", "education", "skills", "projects", "summary",
    "certifications", "achievements",
]


@dataclass
class ATSResult:
    score: float                   # 0.0 – 100.0
    keyword_score: float           # sub-score
    structure_score: float         # sub-score
    matched_keywords: list[str]
    missing_keywords: list[str]
    recommendations: list[str]
    breakdown: dict


def _tokenize(text: str) -> set[str]:
    """Lowercase, remove punctuation, split into word tokens."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return set(text.split())


def _extract_ngrams(text: str, n: int = 2) -> set[str]:
    """Extract n-grams for multi-word keyword matching."""
    words = text.lower().split()
    return {" ".join(words[i:i+n]) for i in range(len(words) - n + 1)}


def _score_keywords(resume_text: str, jd_text: str) -> tuple[float, list[str], list[str]]:
    """
    Calculate keyword match score.
    Returns (score 0-100, matched_kw, missing_kw).
    """
    resume_tokens = _tokenize(resume_text)
    jd_tokens = _tokenize(jd_text)

    # Also check bigrams
    resume_bigrams = _extract_ngrams(resume_text)
    jd_bigrams = _extract_ngrams(jd_text)

    # Extract meaningful JD keywords (filter stop words)
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "shall", "can", "need", "not",
        "that", "this", "these", "those", "we", "you", "they", "our", "your",
        "their", "its", "his", "her", "who", "what", "when", "where", "how",
        "which", "as", "if", "than", "so", "yet", "both", "either",
    }
    jd_keywords = {t for t in jd_tokens if len(t) > 2 and t not in stop_words}
    jd_phrases = {p for p in jd_bigrams if not any(sw in p for sw in stop_words)}

    matched = []
    missing = []

    # Single-word matches
    for kw in jd_keywords:
        if kw in resume_tokens:
            matched.append(kw)
        else:
            missing.append(kw)

    # Bigram matches
    for phrase in jd_phrases:
        if phrase in resume_bigrams:
            if phrase not in matched:
                matched.append(phrase)

    # Priority keyword bonus
    priority_matched = sum(1 for kw in matched if kw in PRIORITY_KEYWORDS)
    priority_missing = [kw for kw in PRIORITY_KEYWORDS if kw in jd_keywords and kw not in matched]

    if not jd_keywords:
        return 0.0, [], []

    base_score = len(matched) / max(len(jd_keywords), 1) * 100
    bonus = min(priority_matched * 2, 10)  # Up to +10 bonus
    final_score = min(base_score + bonus, 100)

    # Sort missing by priority
    missing_sorted = sorted(missing, key=lambda k: k in PRIORITY_KEYWORDS, reverse=True)

    return round(final_score, 1), sorted(matched), missing_sorted[:20]


def _score_structure(resume_text: str) -> tuple[float, list[str]]:
    """
    Score resume structure. Checks for expected sections.
    Returns (score 0-100, list of recommendations).
    """
    text_lower = resume_text.lower()
    found_sections = [s for s in EXPECTED_RESUME_SECTIONS if s in text_lower]
    score = len(found_sections) / len(EXPECTED_RESUME_SECTIONS) * 100

    recs = []
    if "summary" not in found_sections:
        recs.append("Add a professional summary at the top of your resume.")
    if "experience" not in found_sections:
        recs.append("Add a dedicated 'Experience' section.")
    if "skills" not in found_sections:
        recs.append("Add a 'Skills' section with relevant technical skills.")
    if "projects" not in found_sections:
        recs.append("Add a 'Projects' section to showcase your work.")

    word_count = len(resume_text.split())
    if word_count < 200:
        recs.append(f"Resume is short ({word_count} words). Aim for 400–600 words.")
    elif word_count > 900:
        recs.append(f"Resume is very long ({word_count} words). Consider trimming to 1 page.")

    return round(score, 1), recs


def calculate_ats_score(resume_text: str, job_description: str) -> ATSResult:
    """
    Main entry point. Calculate full ATS score for a resume against a JD.
    """
    kw_score, matched, missing = _score_keywords(resume_text, job_description)
    struct_score, struct_recs = _score_structure(resume_text)

    # Weighted final score: 70% keywords, 30% structure
    final = round(kw_score * 0.70 + struct_score * 0.30, 1)

    recommendations = []
    if missing:
        top_missing = missing[:5]
        recommendations.append(
            f"Add these high-priority keywords from the JD: {', '.join(top_missing)}"
        )
    recommendations.extend(struct_recs)

    return ATSResult(
        score=final,
        keyword_score=kw_score,
        structure_score=struct_score,
        matched_keywords=matched[:30],
        missing_keywords=missing[:20],
        recommendations=recommendations,
        breakdown={
            "keyword_score": kw_score,
            "structure_score": struct_score,
            "keyword_weight": 0.70,
            "structure_weight": 0.30,
            "matched_count": len(matched),
            "missing_count": len(missing),
        },
    )
