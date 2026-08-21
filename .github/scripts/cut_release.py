"""Apply the five-file release-hygiene bump for a chore(release) commit."""

import argparse
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The README release block is inserted right under this line.
README_ANCHOR = (
    "> The complete, versioned history is maintained in **[CHANGELOG.md](./CHANGELOG.md)**."
)


def sub_once(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text()
    new, hits = re.subn(pattern, replacement, text, count=1)
    if hits != 1 or new == text:
        sys.exit(f"{path.relative_to(ROOT)}: expected exactly one match for {pattern!r}")
    path.write_text(new)


def changelog_bullets(changelog: str, version: str) -> list[str]:
    section = re.search(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[)", changelog, re.S | re.M
    )
    body = section.group(1) if section else ""
    return [line for line in body.splitlines() if line.startswith("- ")]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument(
        "--highlights",
        default="",
        help="README bullets, one per line; defaults to the CHANGELOG entries",
    )
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    args = parser.parse_args()

    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        sys.exit(f"not a semver version: {args.version}")

    config = ROOT / "backend/app/core/config.py"
    current = re.search(r'VERSION: str = "([^"]+)"', config.read_text())
    if not current:
        sys.exit("config.py: VERSION constant not found")
    if current.group(1) == args.version:
        sys.exit(f"already at {args.version} — nothing to bump")

    changelog = ROOT / "CHANGELOG.md"
    if f"## [{args.version}]" in changelog.read_text():
        sys.exit(f"CHANGELOG.md already has a {args.version} section")

    sub_once(config, r'VERSION: str = "[^"]+"', f'VERSION: str = "{args.version}"')
    sub_once(ROOT / "docs/API.md", r'"version": "[^"]+"', f'"version": "{args.version}"')
    sub_once(
        changelog,
        r"## \[Unreleased\]",
        f"## [Unreleased]\n\n## [{args.version}] - {args.date}",
    )
    sub_once(
        ROOT / "INFRASTRUCTURE.md",
        r"> Last updated: \S+ \| Platform version: v\S+ \|",
        f"> Last updated: {args.date} | Platform version: v{args.version} |",
    )

    bullets = [line.strip() for line in args.highlights.splitlines() if line.strip()]
    bullets = [b if b.startswith("- ") else f"- {b}" for b in bullets]
    if not bullets:
        bullets = changelog_bullets(changelog.read_text(), args.version)
    if not bullets:
        sys.exit("nothing for the README block — pass --highlights or fill [Unreleased] first")

    readme = ROOT / "README.md"
    text = readme.read_text()
    if README_ANCHOR not in text:
        sys.exit("README.md: release-history anchor line not found")
    block = f"### v{args.version} — {args.title}\n" + "\n".join(bullets)
    readme.write_text(text.replace(README_ANCHOR, f"{README_ANCHOR}\n\n{block}", 1))

    print(f"bumped {current.group(1)} -> {args.version} across the five release files")


if __name__ == "__main__":
    main()
