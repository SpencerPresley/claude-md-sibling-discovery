"""Packaging contract tests for skills exposed through the Skills CLI."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTABLE_SKILLS = (
    ROOT / "plugins" / "fix-docstrings" / "skills" / "fix-docstrings",
    ROOT / "plugins" / "llm-input-engineering" / "skills" / "context-engineering",
    ROOT / "plugins" / "llm-input-engineering" / "skills" / "prompt-engineering",
    ROOT / "plugins" / "using-codex-cli" / "skills" / "using-codex-cli",
)


def relative_links(path: Path) -> set[Path]:
    """Return the resolved local Markdown targets linked by a document."""
    targets = set()
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text()):
        if "://" in target or target.startswith("#"):
            continue
        targets.add((path.parent / target.split("#", 1)[0]).resolve())
    return targets


class PortableSkillContractTests(unittest.TestCase):
    """Ensure a selected skill remains complete after directory-only install."""

    def test_skill_links_do_not_escape_the_installed_directory(self) -> None:
        for skill_dir in PORTABLE_SKILLS:
            for target in relative_links(skill_dir / "SKILL.md"):
                self.assertTrue(
                    target.is_relative_to(skill_dir.resolve()),
                    f"{skill_dir.relative_to(ROOT)} links outside its install boundary: {target}",
                )

    def test_every_bundled_reference_is_reachable_from_skill_md(self) -> None:
        for skill_dir in PORTABLE_SKILLS:
            linked = relative_links(skill_dir / "SKILL.md")
            for reference in (skill_dir / "references").glob("*.md"):
                self.assertIn(
                    reference.resolve(),
                    linked,
                    f"{reference.relative_to(ROOT)} is copied but unreachable from SKILL.md",
                )


if __name__ == "__main__":
    unittest.main()
