"""Loader for the labeled resume/job evaluation corpus."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "datasets"
RESUME_DIR = DATA_DIR / "resumes"
JOB_DIR = DATA_DIR / "jobs"
PAIRS_FILE = DATA_DIR / "ats_pairs.jsonl"

# strong: the resume is a real candidate for the job.
# related: same broad field, wrong role — the genuinely hard case.
# weak: different discipline, or out of domain entirely.
RELATIONS = ("strong", "related", "weak")


@dataclass(frozen=True)
class Pair:
    """One labeled resume/job combination, text already resolved."""

    resume_id: str
    job_id: str
    relation: str
    note: str
    resume_text: str
    job_text: str

    @property
    def label(self) -> str:
        return f"{self.resume_id} x {self.job_id}"


def _read(directory: Path, name: str, kind: str) -> str:
    path = directory / f"{name}.txt"
    if not path.is_file():
        raise FileNotFoundError(f"{kind} fixture {name!r} referenced by the corpus is missing")
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def load_ats_pairs() -> tuple[Pair, ...]:
    """Read the pair labels and resolve each side to its fixture text.

    Strict on purpose: a corpus that silently drops a malformed row produces a
    scorecard that looks healthy because it measured less than you think.
    """
    if not PAIRS_FILE.is_file():
        raise FileNotFoundError(f"corpus file not found: {PAIRS_FILE}")

    pairs: list[Pair] = []
    for lineno, line in enumerate(PAIRS_FILE.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{PAIRS_FILE.name}:{lineno} is not valid JSON: {exc}") from exc

        relation = row.get("relation")
        if relation not in RELATIONS:
            raise ValueError(
                f"{PAIRS_FILE.name}:{lineno} has relation {relation!r}, expected one of {RELATIONS}"
            )

        pairs.append(
            Pair(
                resume_id=row["resume"],
                job_id=row["job"],
                relation=relation,
                note=row.get("note", ""),
                resume_text=_read(RESUME_DIR, row["resume"], "resume"),
                job_text=_read(JOB_DIR, row["job"], "job"),
            )
        )

    if not pairs:
        raise ValueError(f"{PAIRS_FILE.name} contains no pairs")
    return tuple(pairs)
