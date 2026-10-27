"""Prepare and validate all five release-file edits before writing them."""

import argparse
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README_ANCHOR = (
    "> The complete, versioned history is maintained in **[CHANGELOG.md](./CHANGELOG.md)**."
)


def replace_once(text: str, pattern: str, replacement: str, filename: str) -> str:
    new, hits = re.subn(pattern, lambda _match: replacement, text, count=1, flags=re.M)
    if hits != 1 or new == text:
        raise ValueError(f"{filename}: expected a changed match for {pattern!r}")
    return new


def changelog_bullets(changelog: str, version: str) -> list[str]:
    section = re.search(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", changelog, re.S | re.M
    )
    body = section.group(1) if section else ""
    return [line for line in body.splitlines() if line.startswith("- ")]


def prepare_release(root: Path, version: str, title: str, date: str, highlights: str) -> dict:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"not a semver version: {version}")
    if not title.strip() or "\n" in title or "\r" in title:
        raise ValueError("title must be a nonempty single line")
    if datetime.date.fromisoformat(date).isoformat() != date:
        raise ValueError("date must use YYYY-MM-DD")

    names = (
        "backend/app/core/config.py",
        "docs/API.md",
        "CHANGELOG.md",
        "INFRASTRUCTURE.md",
        "README.md",
    )
    original = {name: (root / name).read_text() for name in names}
    current = re.search(r'VERSION: str = "(\d+\.\d+\.\d+)"', original[names[0]])
    if not current:
        raise ValueError("config.py: VERSION constant not found")
    if tuple(map(int, version.split("."))) <= tuple(map(int, current.group(1).split("."))):
        raise ValueError(f"version must advance beyond {current.group(1)}")
    if re.search(rf"^## \[{re.escape(version)}\]", original["CHANGELOG.md"], re.M):
        raise ValueError(f"CHANGELOG.md already has a {version} section")

    updated = {
        names[0]: replace_once(
            original[names[0]], r'VERSION: str = "[^"]+"', f'VERSION: str = "{version}"', names[0]
        ),
        names[1]: replace_once(
            original[names[1]], r'"version": "[^"]+"', f'"version": "{version}"', names[1]
        ),
        names[2]: replace_once(
            original[names[2]],
            r"^## \[Unreleased\]",
            f"## [Unreleased]\n\n## [{version}] - {date}",
            names[2],
        ),
        names[3]: replace_once(
            original[names[3]],
            r"^> Last updated: \S+ \| Platform version: v\S+ \|",
            f"> Last updated: {date} | Platform version: v{version} |",
            names[3],
        ),
    }
    bullets = [line.strip() for line in highlights.splitlines() if line.strip()]
    bullets = [b if b.startswith("- ") else f"- {b}" for b in bullets]
    if not bullets:
        bullets = changelog_bullets(updated["CHANGELOG.md"], version)
    if not bullets:
        raise ValueError(
            "nothing for the README block — pass --highlights or fill [Unreleased] first"
        )

    readme = original["README.md"]
    if readme.count(README_ANCHOR) != 1:
        raise ValueError("README.md: expected one release-history anchor line")
    start = readme.index(README_ANCHOR) + len(README_ANCHOR)
    next_section = re.search(r"^## ", readme[start:], re.M)
    end = start + next_section.start() if next_section else len(readme)
    block = f"### v{version} — {title.strip()}\n" + "\n".join(bullets)
    updated["README.md"] = readme[:start] + f"\n\n{block}\n\n" + readme[end:]
    return {root / name: text for name, text in updated.items()}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument(
        "--highlights",
        default="",
        help="README bullets, one per line; defaults to CHANGELOG entries",
    )
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    args = parser.parse_args(argv)
    try:
        changes = prepare_release(ROOT, args.version, args.title, args.date, args.highlights)
    except (ValueError, OSError) as error:
        sys.exit(str(error))
    for path, text in changes.items():
        path.write_text(text)
    print(f"prepared {args.version} across the five release files")


if __name__ == "__main__":
    main()
