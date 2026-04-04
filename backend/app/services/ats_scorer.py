"""
ATS Scorer — hybrid semantic + keyword + structure scoring.

Weights:
  50%  Semantic similarity  — sentence-transformers cosine similarity
  30%  Keyword match        — exact + bigram overlap
  20%  Structure heuristics — section presence and length

Falls back to 80/20 keyword/structure if the embedding model fails to load.
"""
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any


logger = logging.getLogger(__name__)

# ─── Model Configuration ──────────────────────────────────────────────────────
# all-MiniLM-L6-v2: 80MB, 384-dim, excellent speed/quality tradeoff for CPU
# Downloaded once and cached at ~/.cache/huggingface/
MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model() -> Any:
    """Load model once and reuse across requests (lru_cache = singleton).

    Import is inside this function so torch only loads on first ATS request,
    not at app startup. The lru_cache ensures it's loaded at most once.
    """
    from sentence_transformers import SentenceTransformer  # lazy import
    logger.info(f"Loading sentence-transformers model: {MODEL_NAME}")
    return SentenceTransformer(MODEL_NAME)


# ─── Constants ────────────────────────────────────────────────────────────────
PRIORITY_KEYWORDS = {
    "python", "sql", "machine learning", "deep learning", "nlp", "pytorch",
    "tensorflow", "docker", "kubernetes", "aws", "azure", "gcp",
    "fastapi", "django", "flask", "react", "typescript", "ci/cd",
    "data science", "ai", "llm", "rag", "fine-tuning", "mlops",
    "spark", "hadoop", "airflow", "dbt", "kafka", "elasticsearch",
    "pandas", "numpy", "scikit-learn", "xgboost", "lightgbm",
}

SECTION_PATTERNS = {
    "experience": r"\b(experience|employment|work history|career)\b",
    "education":  r"\b(education|degree|university|bachelor|master|phd)\b",
    "skills":     r"\b(skills|technologies|tech stack|competencies)\b",
    "projects":   r"\b(projects|portfolio|open.?source)\b",
    "summary":    r"\b(summary|objective|profile|about me)\b",
    "certifications": r"\b(certifications?|licenses?|credentials)\b",
}

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "not",
    "that", "this", "these", "those", "we", "you", "they", "our", "your",
    "their", "its", "who", "what", "when", "where", "how", "which",
}


@dataclass
class ATSResult:
    score: float                        # 0–100 composite
    semantic_score: float               # sentence-transformer cosine sim (0–100)
    keyword_score: float                # keyword overlap (0–100)
    structure_score: float              # section/length heuristics (0–100)
    matched_keywords: list[str]
    missing_keywords: list[str]
    recommendations: list[str]
    section_scores: dict                # per-section semantic similarity
    breakdown: dict


# ─── Semantic Similarity ──────────────────────────────────────────────────────

def _cosine_similarity(a: Any, b: Any) -> float:
    """Numerically stable cosine similarity."""
    import numpy as np  # lazy import — torch/numpy only loaded on first ATS request
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _score_semantic(resume_text: str, jd_text: str) -> tuple[float, dict]:
    """
    Compute semantic similarity between resume and JD using dense embeddings.

    Also computes section-level scores by extracting named sections from the
    resume and comparing each against the full JD — tells the user which
    sections are well-aligned and which need work.

    Returns: (overall_score 0-100, section_scores dict)
    """
    model = _get_model()

    # Overall similarity
    resume_emb, jd_emb = model.encode([resume_text, jd_text], show_progress_bar=False)
    overall_sim = _cosine_similarity(resume_emb, jd_emb)
    overall_score = round(overall_sim * 100, 1)

    # Section-level breakdown
    section_scores: dict[str, float] = {}
    resume_lower = resume_text.lower()

    for section_name, pattern in SECTION_PATTERNS.items():
        match = re.search(pattern, resume_lower)
        if not match:
            section_scores[section_name] = 0.0
            continue

        # Extract ~500 chars after the section header as the section content
        start = match.start()
        snippet = resume_text[start : start + 600].strip()
        if len(snippet) < 30:
            section_scores[section_name] = 0.0
            continue

        sec_emb = model.encode([snippet], show_progress_bar=False)[0]
        sim = _cosine_similarity(sec_emb, jd_emb)
        section_scores[section_name] = round(sim * 100, 1)

    return overall_score, section_scores


# ─── Keyword Matching (kept as recall signal) ─────────────────────────────────

def _tokenize(text: str) -> set[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return set(text.split())


def _extract_ngrams(text: str, n: int = 2) -> set[str]:
    words = text.lower().split()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def _score_keywords(resume_text: str, jd_text: str) -> tuple[float, list[str], list[str]]:
    resume_tokens = _tokenize(resume_text)
    jd_tokens = _tokenize(jd_text)
    resume_bigrams = _extract_ngrams(resume_text)
    jd_bigrams = _extract_ngrams(jd_text)

    jd_keywords = {t for t in jd_tokens if len(t) > 2 and t not in STOP_WORDS}
    jd_phrases = {p for p in jd_bigrams if not any(sw in p.split() for sw in STOP_WORDS)}

    matched: list[str] = []
    missing: list[str] = []

    for kw in jd_keywords:
        if kw in resume_tokens:
            matched.append(kw)
        else:
            missing.append(kw)

    for phrase in jd_phrases:
        if phrase in resume_bigrams and phrase not in matched:
            matched.append(phrase)

    priority_matched = sum(1 for kw in matched if kw in PRIORITY_KEYWORDS)

    if not jd_keywords:
        return 0.0, [], []

    base_score = len(matched) / max(len(jd_keywords), 1) * 100
    bonus = min(priority_matched * 2, 10)
    final_score = min(base_score + bonus, 100)

    # Sort missing: priority keywords first, then alphabetical
    missing_sorted = sorted(missing, key=lambda k: (k not in PRIORITY_KEYWORDS, k))
    return round(final_score, 1), sorted(matched), missing_sorted[:20]


# ─── Structure Scoring ────────────────────────────────────────────────────────

def _score_structure(resume_text: str) -> tuple[float, list[str]]:
    text_lower = resume_text.lower()
    found = [s for s, pat in SECTION_PATTERNS.items() if re.search(pat, text_lower)]
    score = len(found) / len(SECTION_PATTERNS) * 100

    recs: list[str] = []
    if "summary" not in found:
        recs.append("Add a professional summary at the top of your resume.")
    if "experience" not in found:
        recs.append("Add a dedicated 'Experience' section.")
    if "skills" not in found:
        recs.append("Add a 'Skills' section with relevant technical skills.")
    if "projects" not in found:
        recs.append("Consider adding a 'Projects' section to showcase practical work.")

    word_count = len(resume_text.split())
    if word_count < 200:
        recs.append(f"Resume is very short ({word_count} words). Aim for 400–600 words.")
    elif word_count > 900:
        recs.append(f"Resume is long ({word_count} words). Consider trimming to one page.")

    return round(score, 1), recs


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def calculate_ats_score(resume_text: str, job_description: str) -> ATSResult:
    """
    Full ATS score — hybrid semantic + keyword + structure.

    Scoring weights:
        Semantic similarity   50%  (sentence-transformers, catches synonyms)
        Keyword match         30%  (exact recall, what literal ATS systems check)
        Structure heuristics  20%  (section presence, length)
    """
    try:
        semantic_score, section_scores = _score_semantic(resume_text, job_description)
    except Exception as exc:
        # Graceful degradation: fall back to keyword-only if model fails
        logger.warning(f"Semantic scoring failed, falling back to keyword-only: {exc}")
        semantic_score = 0.0
        section_scores = {}

    kw_score, matched, missing = _score_keywords(resume_text, job_description)
    struct_score, struct_recs = _score_structure(resume_text)

    # Composite — if semantic scoring failed, shift weight to keyword
    if semantic_score == 0.0:
        final = round(kw_score * 0.80 + struct_score * 0.20, 1)
        kw_weight, sem_weight = 0.80, 0.0
    else:
        final = round(
            semantic_score * 0.50 + kw_score * 0.30 + struct_score * 0.20, 1
        )
        kw_weight, sem_weight = 0.30, 0.50

    recommendations: list[str] = []
    if missing:
        top_missing = missing[:5]
        recommendations.append(
            f"Add these high-priority keywords from the JD: {', '.join(top_missing)}"
        )

    # Semantic-aware recommendations
    if semantic_score > 0 and semantic_score < 50:
        recommendations.append(
            "Your resume has low semantic alignment with this JD. "
            "Rewrite key bullet points to use the same language as the job posting."
        )

    weak_sections = [
        sec for sec, score in section_scores.items()
        if 0 < score < 40
    ]
    if weak_sections:
        recommendations.append(
            f"These sections have low alignment with the JD: {', '.join(weak_sections)}. "
            "Consider adding more relevant content to them."
        )

    recommendations.extend(struct_recs)

    return ATSResult(
        score=final,
        semantic_score=semantic_score,
        keyword_score=kw_score,
        structure_score=struct_score,
        matched_keywords=matched[:30],
        missing_keywords=missing[:20],
        recommendations=recommendations,
        section_scores=section_scores,
        breakdown={
            "semantic_score": semantic_score,
            "keyword_score": kw_score,
            "structure_score": struct_score,
            "semantic_weight": sem_weight,
            "keyword_weight": kw_weight,
            "structure_weight": 0.20,
            "matched_count": len(matched),
            "missing_count": len(missing),
            "model": MODEL_NAME,
        },
    )
