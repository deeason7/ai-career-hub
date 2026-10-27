"""Regression checks for documentation drift without application dependencies."""

import contextlib
import importlib.util
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "check_docs", Path(__file__).resolve().parents[1] / "check_docs.py"
)
docs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(docs)


class DocsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def write(self, filename: str, text: str) -> Path:
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def release_files(self):
        return [
            self.write("backend/app/core/config.py", '    VERSION: str = "4.4.3"\n'),
            self.write("docs/API.md", '```json\n{"version": "4.4.3"}\n```\n'),
            self.write("README.md", "### v4.4.3 — Latest\n### v3.0.0 — Historical\n"),
            self.write("INFRASTRUCTURE.md", "> Platform version: v4.4.3\n### v3.1 — History\n"),
            self.write("CHANGELOG.md", "## [Unreleased]\n## [4.4.3] - 2026-08-22\n## [3.0.0]\n"),
        ]

    def test_relative_links_headings_duplicates_and_explicit_anchors_pass(self):
        self.write(
            "docs/Guide.md",
            '# Guide\n## Health & meta\n## Health & meta\n### `GET /health`\n<a id="custom"></a>\n',
        )
        source = self.write(
            "README.md",
            "[guide](docs/Guide.md)\n[health](docs/Guide.md#health--meta)\n"
            "[duplicate](docs/Guide.md#health--meta-1)\n[route](docs/Guide.md#get-health)\n"
            "[custom](docs/Guide.md#custom)\n[docs](docs/)\n",
        )
        self.assertEqual(docs.check_links(self.root, [source]), [])

    def test_missing_local_file_has_actionable_source_line(self):
        source = self.write("README.md", "# Readme\n\n[guide](docs/missing.md)\n")
        self.assertEqual(
            docs.check_links(self.root, [source]),
            ["README.md:3: missing local target: docs/missing.md"],
        )

    def test_missing_heading_is_reported_even_when_target_exists(self):
        self.write("docs/Guide.md", "# Guide\n")
        source = self.write("README.md", "[wrong](docs/Guide.md#renamed-heading)\n")
        self.assertEqual(
            docs.check_links(self.root, [source]),
            ["README.md:1: missing heading anchor: docs/Guide.md#renamed-heading"],
        )

    def test_code_examples_comments_and_external_urls_are_ignored(self):
        source = self.write(
            "README.md",
            "```markdown\n[example](missing.md)\n# Hidden heading\n```\n"
            "~~~md\n[example](other.md)\n~~~\n`[inline](absent.md)`\n"
            "<!-- [draft](draft.md) -->\n[remote](https://example.org/no-page#no-heading)\n"
            "[email](mailto:example@example.org)\n[host](//example.org/missing)\n",
        )
        self.assertEqual(docs.check_links(self.root, [source]), [])
        self.assertNotIn("hidden-heading", docs.heading_anchors(source.read_text()))

    def test_reference_destinations_and_encoded_paths_are_checked(self):
        self.write("docs/Guide (local).md", "# A title\n")
        source = self.write(
            "README.md",
            '[guide](<docs/Guide (local).md#a-title> "title")\n'
            "[encoded](docs/Guide%20%28local%29.md#a-title)\n"
            '[guide]: <docs/Guide (local).md#a-title> "title"\n'
            "[broken]: missing.md\n",
        )
        self.assertEqual(
            docs.check_links(self.root, [source]),
            ["README.md:4: missing local target: missing.md"],
        )

    def test_current_markers_match_without_rewriting_history(self):
        self.release_files()
        self.assertEqual(docs.check_versions(self.root), ([], "4.4.3"))

    def test_each_of_five_version_carriers_detects_drift(self):
        for filename, _, _ in docs.RELEASE_MARKERS:
            with self.subTest(filename=filename):
                self.release_files()
                path = self.root / filename
                path.write_text(path.read_text().replace("4.4.3", "4.4.2", 1))
                problems, _ = docs.check_versions(self.root)
                self.assertTrue(problems)
                self.assertTrue(all("expected" in problem for problem in problems))

    def test_missing_version_marker_fails(self):
        self.release_files()
        self.write("README.md", "# Missing release heading\n")
        problems, _ = docs.check_versions(self.root)
        self.assertEqual(
            problems, ["README.md:1: missing current release marker: latest release heading"]
        )

    def test_cli_returns_nonzero_for_broken_links_and_version_drift(self):
        for content in ("### v4.4.3\n[missing](missing.md)\n", "### v4.4.2\n"):
            with self.subTest(content=content):
                files = self.release_files()
                self.write("README.md", content)
                error = io.StringIO()
                with patch.object(docs, "markdown_files", return_value=files[1:]):
                    with contextlib.redirect_stderr(error):
                        self.assertEqual(docs.main(["--root", str(self.root)]), 1)
                self.assertIn("README.md:", error.getvalue())

    def test_cli_returns_zero_for_valid_documentation(self):
        files = self.release_files()
        output = io.StringIO()
        with patch.object(docs, "markdown_files", return_value=files[1:]):
            with contextlib.redirect_stdout(output):
                self.assertEqual(docs.main(["--root", str(self.root)]), 0)
        self.assertIn("4 Markdown files; five release markers at v4.4.3", output.getvalue())

    def test_discovery_includes_new_source_docs_and_excludes_ignored_files(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        tracked = self.write("README.md", "# Readme\n")
        deleted = self.write("deleted.md", "# Deleted\n")
        self.write(".gitignore", "ignored/\n")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, capture_output=True)
        deleted.unlink()
        new = self.write("docs/new.md", "# New document\n")
        self.write("ignored/cache.md", "# Not source\n")
        self.assertEqual(docs.markdown_files(self.root), sorted([tracked, new]))


if __name__ == "__main__":
    unittest.main()
