"""Contract tests for the public llm-input-engineering plugin."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "llm-input-engineering"
SKILLS = (
    PLUGIN / "skills" / "prompt-engineering" / "SKILL.md",
    PLUGIN / "skills" / "context-engineering" / "SKILL.md",
)


class LlmInputEngineeringContractTests(unittest.TestCase):
    """Keep the public plugin narrow, portable, and internally linked."""

    def test_marketplace_and_root_readme_expose_plugin(self) -> None:
        marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
        entries = {entry["name"]: entry for entry in marketplace["plugins"]}
        manifest = json.loads(
            (PLUGIN / ".claude-plugin" / "plugin.json").read_text(),
        )

        self.assertEqual(
            entries["llm-input-engineering"]["source"],
            "./plugins/llm-input-engineering",
        )
        self.assertEqual(manifest["name"], "llm-input-engineering")
        self.assertEqual(
            manifest["version"],
            entries["llm-input-engineering"]["version"],
        )
        self.assertIn(
            "llm-input-engineering",
            (ROOT / "README.md").read_text(),
        )

    def test_skill_descriptions_are_narrow_triggers(self) -> None:
        descriptions = []
        for skill in SKILLS:
            text = skill.read_text()
            match = re.search(r"^description: (.+)$", text, re.MULTILINE)
            self.assertIsNotNone(match, skill)
            descriptions.append(match.group(1))
            self.assertEqual(len(re.findall(r"^# ", text, re.MULTILINE)), 1)

        self.assertTrue(all(value.startswith("Use when ") for value in descriptions))
        self.assertNotIn(
            "make a model understand or perform a task better",
            "\n".join(descriptions),
        )

    def test_public_material_has_no_private_checkout_residue(self) -> None:
        rejected = (
            "/Users/",
            "atlascyber",
            "AtlasCyber",
            "anthropic.com",
            ".claude/worktrees",
        )
        for path in PLUGIN.rglob("*.md"):
            text = path.read_text()
            for marker in rejected:
                self.assertNotIn(marker, text, f"{marker!r} found in {path}")

    def test_all_relative_markdown_links_resolve(self) -> None:
        for path in PLUGIN.rglob("*.md"):
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text()):
                if "://" in target or target.startswith("#"):
                    continue
                resolved = (path.parent / target.split("#", 1)[0]).resolve()
                self.assertTrue(
                    resolved.exists(),
                    f"{path.relative_to(ROOT)} -> {target}",
                )

    def test_case_study_preserves_the_engine_specific_correction(self) -> None:
        case_study = (
            PLUGIN
            / "skills"
            / "context-engineering"
            / "references"
            / "devstral-langchain-case-study.md"
        ).read_text()

        self.assertIn(
            "BOS -> system -> tools -> conversation",
            case_study,
        )
        self.assertIn(
            "system / earlier conversation -> tools -> final user",
            case_study,
        )
        self.assertIn(
            "does **not** put tools after the final user content",
            case_study,
        )


if __name__ == "__main__":
    unittest.main()
