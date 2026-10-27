"""Release edits remain complete, bounded and safe on invalid input."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "cut_release", Path(__file__).resolve().parents[1] / "cut_release.py"
)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.files = {
            "backend/app/core/config.py": '    VERSION: str = "4.4.3"\n',
            "docs/API.md": '{"version": "4.4.3"}\n',
            "CHANGELOG.md": "## [Unreleased]\n\n### Fixed\n- A useful fix\n\n## [4.4.3]\n- History\n",
            "INFRASTRUCTURE.md": "> Last updated: 2026-08-22 | Platform version: v4.4.3 | AWS\n",
            "README.md": (
                "# Product\n\n## Release History\n\n"
                + release.README_ANCHOR
                + "\n\n### v4.4.3 — Old release\n- Old summary\n\n## License\nMIT\n"
            ),
        }
        for name, text in self.files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def snapshot(self):
        return {name: (self.root / name).read_text() for name in self.files}

    def run_release(self, *extra):
        with patch.object(release, "ROOT", self.root):
            release.main(
                ["--version", "4.4.4", "--title", "Recovery", "--date", "2026-10-26", *extra]
            )

    def test_success_updates_five_files_and_keeps_history_and_other_sections(self):
        self.run_release()
        result = self.snapshot()
        self.assertTrue(all(result[name] != before for name, before in self.files.items()))
        self.assertIn("## [4.4.3]\n- History", result["CHANGELOG.md"])
        self.assertIn("### v4.4.4 — Recovery\n- A useful fix", result["README.md"])
        self.assertNotIn("### v4.4.3", result["README.md"])
        self.assertTrue(result["README.md"].startswith("# Product\n"))
        self.assertTrue(result["README.md"].endswith("## License\nMIT\n"))

    def test_second_release_does_not_grow_readme_history(self):
        self.run_release()
        with patch.object(release, "ROOT", self.root):
            release.main(["--version", "4.4.5", "--title", "Next", "--highlights", "Another fix"])
        result = self.snapshot()
        self.assertEqual(result["README.md"].count("### v"), 1)
        self.assertIn("### v4.4.5", result["README.md"])
        self.assertIn("## [4.4.4]", result["CHANGELOG.md"])
        self.assertIn("## [4.4.3]", result["CHANGELOG.md"])

    def test_missing_readme_anchor_does_not_partially_write_release(self):
        (self.root / "README.md").write_text("# Product\n")
        before = self.snapshot()
        with self.assertRaisesRegex(SystemExit, "anchor"):
            self.run_release()
        self.assertEqual(self.snapshot(), before)

    def test_empty_unreleased_does_not_partially_write_release(self):
        path = self.root / "CHANGELOG.md"
        path.write_text("## [Unreleased]\n\n## [4.4.3]\n- Historical fix\n")
        before = self.snapshot()
        with self.assertRaisesRegex(SystemExit, "nothing for the README"):
            self.run_release()
        self.assertEqual(self.snapshot(), before)

    def test_invalid_version_date_title_or_marker_never_writes(self):
        for extra in (
            ("--version", "4.4.2"),
            ("--version", "4.4.3"),
            ("--date", "2026-02-30"),
            ("--title", ""),
            ("--title", "Bad\nTitle"),
        ):
            with self.subTest(extra=extra):
                before = self.snapshot()
                with self.assertRaises(SystemExit):
                    self.run_release(*extra)
                self.assertEqual(self.snapshot(), before)
        (self.root / "docs/API.md").write_text("Missing metadata\n")
        before = self.snapshot()
        with self.assertRaises(SystemExit):
            self.run_release()
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
