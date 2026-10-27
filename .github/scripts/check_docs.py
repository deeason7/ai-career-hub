"""Check local Markdown links, heading anchors, and the five current release markers.

Uses only the standard library; no application imports, network access, or installed
Markdown tooling are needed. Historical release entries are not current markers.
"""

import argparse
import html
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
RELEASE_MARKERS = (
    ("backend/app/core/config.py", "VERSION", r'^\s*VERSION:\s*str\s*=\s*"(\d+\.\d+\.\d+)"'),
    ("docs/API.md", "API metadata example", r'"version"\s*:\s*"(\d+\.\d+\.\d+)"'),
    ("README.md", "latest release heading", r"^### v(\d+\.\d+\.\d+)\b"),
    ("INFRASTRUCTURE.md", "platform banner", r"^>.*Platform version:\s*v(\d+\.\d+\.\d+)\b"),
    ("CHANGELOG.md", "latest release heading", r"^## \[(\d+\.\d+\.\d+)\]"),
)
# Inline destinations support angle brackets, escaped characters, and one level
# of parentheses. Reference definitions are checked whether or not used yet.
INLINE_LINK = re.compile(
    r'\]\(\s*(<[^>\n]+>|(?:\\.|[^()\s]|\([^()\n]*\))+)(?:\s+["\'][^\n]*?["\'])?\s*\)'
)
REFERENCE_LINK = re.compile(r"^ {0,3}\[[^\]\n]+\]:\s*(<[^>\n]+>|\S+)", re.M)


def markdown_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.md"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(
        {root / name for name in result.stdout.split("\0") if name and (root / name).is_file()}
    )


def blank(text: str) -> str:
    """Mask syntax while keeping source offsets and diagnostic line numbers."""
    return re.sub(r"[^\n]", " ", text)


def prose(text: str, *, inline_code: bool = False) -> str:
    lines = []
    fence = None
    for line in text.splitlines(keepends=True):
        match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            lines.append(blank(line))
            if re.fullmatch(rf" {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}\s*", line):
                fence = None
        elif match:
            fence = match.group(1)
            lines.append(blank(line))
        else:
            lines.append(line)
    text = re.sub(r"<!--.*?-->", lambda match: blank(match.group()), "".join(lines), flags=re.S)
    if inline_code:
        text = re.sub(r"(`+).*?\1", lambda match: blank(match.group()), text, flags=re.S)
    return text


def heading_anchors(text: str) -> set[str]:
    text = prose(text)
    anchors = set(re.findall(r'<a\b[^>]*\b(?:id|name)=["\']([^"\']+)["\']', text, re.I))
    used = set()
    for match in re.finditer(r"^ {0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", text, re.M):
        heading = re.sub(r"<[^>]*>", "", match.group(1))
        heading = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", heading)
        slug = re.sub(r"[^\w\- ]", "", html.unescape(heading).lower()).replace(" ", "-")
        anchor = slug
        suffix = 0
        while anchor in used:
            suffix += 1
            anchor = f"{slug}-{suffix}"
        used.add(anchor)
        anchors.add(anchor)
    return anchors


def check_links(root: Path, documents: list[Path]) -> list[str]:
    problems = []
    anchors = {}
    for document in documents:
        text = prose(document.read_text(encoding="utf-8"), inline_code=True)
        for pattern in (INLINE_LINK, REFERENCE_LINK):
            for match in pattern.finditer(text):
                destination = re.sub(r"\\(.)", r"\1", match.group(1).strip("<>"))
                url = urlsplit(destination)
                if url.scheme or url.netloc:
                    continue
                local = unquote(url.path)
                target = (
                    root / local.lstrip("/") if local.startswith("/") else document.parent / local
                )
                if not local:
                    target = document
                target = target.resolve()
                location = (
                    f"{document.relative_to(root)}:{text.count(chr(10), 0, match.start()) + 1}"
                )
                if not target.exists():
                    problems.append(f"{location}: missing local target: {destination}")
                elif url.fragment and target.suffix.lower() == ".md" and target.is_file():
                    if target not in anchors:
                        anchors[target] = heading_anchors(target.read_text(encoding="utf-8"))
                    if unquote(url.fragment) not in anchors[target]:
                        problems.append(f"{location}: missing heading anchor: {destination}")
    return problems


def check_versions(root: Path) -> tuple[list[str], str | None]:
    problems = []
    current = None
    for filename, label, pattern in RELEASE_MARKERS:
        path = root / filename
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        match = re.search(pattern, text, re.M)
        if not match:
            problems.append(f"{filename}:1: missing current release marker: {label}")
            continue
        version = match.group(1)
        if filename == "backend/app/core/config.py":
            current = version
        elif current and version != current:
            line = text.count("\n", 0, match.start(1)) + 1
            problems.append(f"{filename}:{line}: {label} is {version}; expected {current}")
    return problems, current


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=ROOT, help="Repository root (default: this checkout)"
    )
    root = parser.parse_args(argv).root.resolve()
    try:
        documents = markdown_files(root)
        problems = check_links(root, documents)
        version_problems, current = check_versions(root)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"{root}:1: documentation check could not run: {error}", file=sys.stderr)
        return 1
    problems.extend(version_problems)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print(
        f"Documentation checks passed: {len(documents)} Markdown files; five release markers at v{current}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
