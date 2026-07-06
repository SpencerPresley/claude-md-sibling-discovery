"""Tests for the claude-md-discovery-extended hook scripts.

Covers the PostToolUse discovery hook (check_claude_md.py) and the
SessionStart/SessionEnd lifecycle scripts.
Run with: uv run pytest tests/ -v
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "hooks" / "scripts"
CHECK_SCRIPT = str(SCRIPTS / "check_claude_md.py")
SESSION_START = str(SCRIPTS / "session_start.py")
SESSION_END = str(SCRIPTS / "session_end.py")

STRIPPED_VARS = (
    "CLAUDE_CONFIG_DIR",
    "CLAUDE_MD_DISCOVERY_STATE_DIR",
    "CLAUDE_MD_DISCOVERY_AGENTS_MD",
    "CLAUDE_MD_DISCOVERY_IGNORE",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_script(script: str, payload: dict, env: dict) -> tuple[int, str, str]:
    """Run a hook script with *payload* as JSON on stdin.

    Returns (exit_code, stdout, stderr).
    """
    proc = subprocess.run(
        [sys.executable, script],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def run_hook(payload: dict, env: dict) -> tuple[int, str, str]:
    return run_script(CHECK_SCRIPT, payload, env)


_sid_counter = 0


def next_sid(label: str = "") -> str:
    global _sid_counter
    _sid_counter += 1
    return f"pytest-{label}-{_sid_counter}-{os.getpid()}"


def build_json(
    *,
    tool: str,
    sid: str,
    cwd: str,
    file_path: str = "",
    path: str = "",
    command: str = "",
    extra_input: dict | None = None,
) -> dict:
    tool_input = {
        "file_path": file_path,
        "path": path,
        "command": command,
    }
    if extra_input:
        tool_input.update(extra_input)
    return {
        "tool_name": tool,
        "session_id": sid,
        "cwd": cwd,
        "tool_input": tool_input,
    }


def ledger_file(env: dict, sid: str) -> Path:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", sid)
    return Path(env["CLAUDE_MD_DISCOVERY_STATE_DIR"]) / f"{safe_id}.jsonl"


def read_ledger(env: dict, sid: str) -> dict[str, dict]:
    """Fold a session ledger into its effective path -> entry mapping."""
    entries: dict[str, dict] = {}
    path = ledger_file(env, sid)
    if not path.is_file():
        return entries
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("p"):
            entries[obj["p"]] = {"h": obj["h"], "k": obj["k"]}
    return entries


def read_log(env: dict, sid: str) -> list[dict]:
    """Parse a session's diagnostic log into a list of event dicts."""
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", sid)
    path = Path(env["CLAUDE_MD_DISCOVERY_STATE_DIR"]) / f"{safe_id}.log"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def hook_env(tmp_path):
    """Isolated environment: state dir and config dir pinned under tmp."""
    env = {k: v for k, v in os.environ.items() if k not in STRIPPED_VARS}
    env["CLAUDE_MD_DISCOVERY_STATE_DIR"] = str(tmp_path / "plugin-state")
    env["CLAUDE_CONFIG_DIR"] = str(tmp_path / "claude-config")
    (tmp_path / "claude-config").mkdir(exist_ok=True)
    return env


@pytest.fixture()
def layout(tmp_path):
    """Create test directory layout:

    tmp/workspace/project/              (cwd)
    tmp/workspace/project/subdir/
    tmp/workspace/sibling/              CLAUDE.md
    tmp/workspace/sibling/deep/nested/  CLAUDE.md
    tmp/workspace/tools/linter/         CLAUDE.md  (cousin)
    tmp/workspace/                      CLAUDE.md  (ancestor of cwd)
    tmp/other-team/services/api/        CLAUDE.md  (unrelated tree)
    """
    project = tmp_path / "workspace" / "project"
    sibling = tmp_path / "workspace" / "sibling"
    deep = sibling / "deep" / "nested"
    cousin = tmp_path / "workspace" / "tools" / "linter"
    unrelated = tmp_path / "other-team" / "services" / "api"

    (project / "subdir").mkdir(parents=True)
    deep.mkdir(parents=True)
    cousin.mkdir(parents=True)
    unrelated.mkdir(parents=True)

    (sibling / "CLAUDE.md").write_text("# sibling\n")
    (tmp_path / "workspace" / "CLAUDE.md").write_text("# parent\n")
    (deep / "CLAUDE.md").write_text("# deep\n")
    (cousin / "CLAUDE.md").write_text("# cousin\n")
    (unrelated / "CLAUDE.md").write_text("# unrelated\n")

    return {
        "project": str(project),
        "sibling": str(sibling),
        "deep": str(deep),
        "cousin": str(cousin),
        "unrelated": str(unrelated),
        "parent": str(tmp_path / "workspace"),
    }


@pytest.fixture()
def worktree_layout(tmp_path):
    """Main repo plus a worktree checkout with byte-identical files:

    tmp/repo/                            CLAUDE.md ("# root")
    tmp/repo/some_dir/                   CLAUDE.md ("# some_dir rules")
    tmp/repo/.worktrees/wt/              CLAUDE.md ("# root")
    tmp/repo/.worktrees/wt/some_dir/     CLAUDE.md ("# some_dir rules")
    """
    repo = tmp_path / "repo"
    wt = repo / ".worktrees" / "wt"
    (repo / "some_dir").mkdir(parents=True)
    (wt / "some_dir").mkdir(parents=True)

    (repo / "CLAUDE.md").write_text("# root\n")
    (repo / "some_dir" / "CLAUDE.md").write_text("# some_dir rules\n")
    (wt / "CLAUDE.md").write_text("# root\n")
    (wt / "some_dir" / "CLAUDE.md").write_text("# some_dir rules\n")

    return {"repo": str(repo), "worktree": str(wt)}


# ---------------------------------------------------------------------------
# Basic validation
# ---------------------------------------------------------------------------

class TestBasicValidation:
    def test_exits_0_on_empty_json(self, hook_env):
        rc, _, _ = run_hook({}, hook_env)
        assert rc == 0

    def test_exits_0_when_tool_name_missing(self, hook_env):
        rc, _, _ = run_hook(
            {"session_id": "x", "cwd": "/tmp", "tool_input": {}}, hook_env
        )
        assert rc == 0

    def test_exits_0_when_session_id_missing(self, hook_env):
        rc, _, _ = run_hook(
            {"tool_name": "Read", "cwd": "/tmp", "tool_input": {}}, hook_env
        )
        assert rc == 0

    def test_exits_0_when_cwd_missing(self, hook_env):
        rc, _, _ = run_hook(
            {"tool_name": "Read", "session_id": "x", "tool_input": {}}, hook_env
        )
        assert rc == 0

    def test_exits_0_for_unknown_tool_type(self, layout, hook_env):
        sid = next_sid("unknown")
        payload = build_json(tool="SomeUnknownTool", sid=sid, cwd=layout["project"])
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 0

    def test_exits_0_when_file_path_empty(self, layout, hook_env):
        sid = next_sid("empty-fp")
        payload = build_json(tool="Read", sid=sid, cwd=layout["project"], file_path="")
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 0

    def test_exits_0_when_path_empty_for_glob(self, layout, hook_env):
        sid = next_sid("empty-path")
        payload = build_json(tool="Glob", sid=sid, cwd=layout["project"], path="")
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 0


# ---------------------------------------------------------------------------
# Project-internal files (should be skipped)
# ---------------------------------------------------------------------------

class TestSkipsProjectFiles:
    def test_skips_file_in_project_root(self, layout, hook_env):
        sid = next_sid("proj-root")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["project"], "file.txt"),
        )
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 0

    def test_skips_file_in_project_subdirectory(self, layout, hook_env):
        sid = next_sid("proj-sub")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["project"], "subdir", "file.txt"),
        )
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 0


# ---------------------------------------------------------------------------
# Ancestor stopping
# ---------------------------------------------------------------------------

class TestAncestorStopping:
    def test_stops_walk_at_ancestor_of_cwd(self, layout, hook_env):
        sid = next_sid("ancestor")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["deep"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        )
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 0


# ---------------------------------------------------------------------------
# Discovery (structured tools)
# ---------------------------------------------------------------------------

class TestDiscovery:
    def test_discovers_sibling_claude_md(self, layout, hook_env):
        sid = next_sid("sibling")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        )
        rc, _, stderr = run_hook(payload, hook_env)
        assert rc == 2
        assert os.path.join(layout["sibling"], "CLAUDE.md") in stderr

    def test_excludes_ancestor_claude_md(self, layout, hook_env):
        sid = next_sid("no-ancestor")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        )
        _, _, stderr = run_hook(payload, hook_env)
        assert os.path.join(layout["sibling"], "CLAUDE.md") in stderr
        assert os.path.join(layout["parent"], "CLAUDE.md") not in stderr

    def test_discovers_multiple_walking_up(self, layout, hook_env):
        sid = next_sid("multi")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["deep"], "file.txt"),
        )
        rc, _, stderr = run_hook(payload, hook_env)
        assert rc == 2
        assert os.path.join(layout["deep"], "CLAUDE.md") in stderr
        assert os.path.join(layout["sibling"], "CLAUDE.md") in stderr

    def test_discovers_cousin_claude_md(self, layout, hook_env):
        sid = next_sid("cousin")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["cousin"], "file.txt"),
        )
        rc, _, stderr = run_hook(payload, hook_env)
        assert rc == 2
        assert os.path.join(layout["cousin"], "CLAUDE.md") in stderr

    def test_discovers_unrelated_tree_claude_md(self, layout, hook_env):
        sid = next_sid("unrelated")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["unrelated"], "file.txt"),
        )
        rc, _, stderr = run_hook(payload, hook_env)
        assert rc == 2
        assert os.path.join(layout["unrelated"], "CLAUDE.md") in stderr

    def test_unrelated_tree_excludes_ancestor_claude_md(self, layout, hook_env):
        sid = next_sid("unrelated-no-ancestor")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["unrelated"], "file.txt"),
        )
        _, _, stderr = run_hook(payload, hook_env)
        assert os.path.join(layout["parent"], "CLAUDE.md") not in stderr

    def test_no_discovery_when_no_claude_md(self, layout, hook_env):
        os.unlink(os.path.join(layout["sibling"], "CLAUDE.md"))
        sid = next_sid("no-cmd")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        )
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 0


# ---------------------------------------------------------------------------
# Tool-specific path extraction
# ---------------------------------------------------------------------------

class TestToolExtraction:
    @pytest.mark.parametrize("tool", ["Read", "Edit", "Write"])
    def test_file_path_tools(self, layout, hook_env, tool):
        sid = next_sid(f"tool-{tool}")
        payload = build_json(
            tool=tool, sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        )
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 2

    @pytest.mark.parametrize("tool", ["Glob", "Grep"])
    def test_path_tools(self, layout, hook_env, tool):
        sid = next_sid(f"tool-{tool}")
        payload = build_json(
            tool=tool, sid=sid, cwd=layout["project"],
            path=layout["sibling"],
        )
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 2


# ---------------------------------------------------------------------------
# Bash tool path extraction
# ---------------------------------------------------------------------------

class TestBashExtraction:
    def test_cat_of_regular_file_discovers(self, layout, hook_env):
        sid = next_sid("bash-cat-file")
        payload = build_json(
            tool="Bash", sid=sid, cwd=layout["project"],
            command=f"cat {layout['sibling']}/file.txt",
        )
        rc, _, stderr = run_hook(payload, hook_env)
        assert rc == 2
        assert os.path.join(layout["sibling"], "CLAUDE.md") in stderr

    def test_ls_directory(self, layout, hook_env):
        sid = next_sid("bash-ls")
        payload = build_json(
            tool="Bash", sid=sid, cwd=layout["project"],
            command=f"ls {layout['sibling']}",
        )
        rc, _, stderr = run_hook(payload, hook_env)
        assert rc == 2
        assert os.path.join(layout["sibling"], "CLAUDE.md") in stderr

    def test_multiple_paths_picks_first_valid(self, layout, hook_env):
        sid = next_sid("bash-multi")
        payload = build_json(
            tool="Bash", sid=sid, cwd=layout["project"],
            command=f"cp {layout['sibling']}/file.txt /nonexistent/place",
        )
        rc, _, stderr = run_hook(payload, hook_env)
        # Should discover via sibling path (first valid)
        assert rc == 2
        assert os.path.join(layout["sibling"], "CLAUDE.md") in stderr

    def test_no_paths_in_command(self, layout, hook_env):
        sid = next_sid("bash-nopath")
        payload = build_json(
            tool="Bash", sid=sid, cwd=layout["project"],
            command="echo hello world",
        )
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 0

    def test_empty_command(self, layout, hook_env):
        sid = next_sid("bash-empty")
        payload = build_json(
            tool="Bash", sid=sid, cwd=layout["project"],
            command="",
        )
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 0

    def test_quoted_path(self, layout, hook_env):
        # Create a directory with a space in the name
        spaced = os.path.join(layout["parent"], "dir with spaces")
        os.makedirs(spaced, exist_ok=True)
        Path(os.path.join(spaced, "CLAUDE.md")).write_text("# spaced\n")

        sid = next_sid("bash-quoted")
        payload = build_json(
            tool="Bash", sid=sid, cwd=layout["project"],
            command=f'cat "{spaced}/file.txt"',
        )
        rc, _, stderr = run_hook(payload, hook_env)
        assert rc == 2
        assert os.path.join(spaced, "CLAUDE.md") in stderr

    def test_tilde_expansion(self, layout, hook_env):
        # This test just verifies tilde paths are expanded; discovery
        # depends on whether ~/... has a CLAUDE.md, so we just check
        # it doesn't crash
        sid = next_sid("bash-tilde")
        payload = build_json(
            tool="Bash", sid=sid, cwd=layout["project"],
            command="cat ~/somefile.txt",
        )
        rc, _, _ = run_hook(payload, hook_env)
        assert rc in (0, 2)  # either is fine

    def test_malformed_quotes_dont_crash(self, layout, hook_env):
        sid = next_sid("bash-malformed")
        payload = build_json(
            tool="Bash", sid=sid, cwd=layout["project"],
            command="echo 'unterminated",
        )
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 0

    def test_bash_targets_project_dir_skipped(self, layout, hook_env):
        sid = next_sid("bash-proj")
        payload = build_json(
            tool="Bash", sid=sid, cwd=layout["project"],
            command=f"cat {layout['project']}/file.txt",
        )
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 0


# ---------------------------------------------------------------------------
# Session deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_second_call_dedupes(self, layout, hook_env):
        sid = next_sid("dedup")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        )
        rc1, _, _ = run_hook(payload, hook_env)
        assert rc1 == 2

        rc2, _, _ = run_hook(payload, hook_env)
        assert rc2 == 0

    def test_different_sessions_report_independently(self, layout, hook_env):
        sid1 = next_sid("indep1")
        sid2 = next_sid("indep2")
        payload1 = build_json(
            tool="Read", sid=sid1, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        )
        payload2 = build_json(
            tool="Read", sid=sid2, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        )
        rc1, _, _ = run_hook(payload1, hook_env)
        rc2, _, _ = run_hook(payload2, hook_env)
        assert rc1 == 2
        assert rc2 == 2


# ---------------------------------------------------------------------------
# Content-hash deduplication (worktrees, clones, copied templates)
# ---------------------------------------------------------------------------

class TestHashDeduplication:
    def test_identical_sibling_content_suppressed(self, layout, hook_env):
        # sibling2 duplicates sibling's CLAUDE.md byte for byte. Once the
        # sibling copy is flagged, the duplicate must stay silent.
        sibling2 = os.path.join(layout["parent"], "sibling2")
        os.makedirs(sibling2)
        Path(sibling2, "CLAUDE.md").write_text("# sibling\n")

        sid = next_sid("hash-dup")
        rc1, _, _ = run_hook(build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        ), hook_env)
        assert rc1 == 2

        rc2, _, stderr2 = run_hook(build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(sibling2, "file.txt"),
        ), hook_env)
        assert rc2 == 0
        assert "CLAUDE.md" not in stderr2

    def test_worktree_duplicates_suppressed(self, worktree_layout, hook_env):
        # Session lives in the worktree; touching the main repo must not
        # flag CLAUDE.md files that are byte-identical to the worktree's.
        sid = next_sid("worktree")
        wt = worktree_layout["worktree"]
        repo = worktree_layout["repo"]

        rc, _, stderr = run_hook(build_json(
            tool="Read", sid=sid, cwd=wt,
            file_path=os.path.join(repo, "some_dir", "file.py"),
        ), hook_env)
        assert rc == 0
        assert "CLAUDE.md" not in stderr

    def test_worktree_after_session_start(self, worktree_layout, hook_env):
        # Same scenario but seeded by the SessionStart hook, as in real use.
        sid = next_sid("worktree-ss")
        wt = worktree_layout["worktree"]
        repo = worktree_layout["repo"]

        rc, _, _ = run_script(SESSION_START, {
            "session_id": sid, "cwd": wt, "source": "startup",
        }, hook_env)
        assert rc == 0

        rc, _, stderr = run_hook(build_json(
            tool="Read", sid=sid, cwd=wt,
            file_path=os.path.join(repo, "some_dir", "file.py"),
        ), hook_env)
        assert rc == 0
        assert "CLAUDE.md" not in stderr

    def test_diverged_worktree_copy_still_flags(self, worktree_layout, hook_env):
        # If the main repo's nested CLAUDE.md differs from the worktree's
        # (diverged branches), it carries different instructions and must
        # still be flagged.
        sid = next_sid("worktree-diverged")
        wt = worktree_layout["worktree"]
        repo = worktree_layout["repo"]
        main_copy = os.path.join(repo, "some_dir", "CLAUDE.md")
        Path(main_copy).write_text("# some_dir rules, main-branch edition\n")

        rc, _, stderr = run_hook(build_json(
            tool="Read", sid=sid, cwd=wt,
            file_path=os.path.join(repo, "some_dir", "file.py"),
        ), hook_env)
        assert rc == 2
        assert main_copy in stderr

    def test_detached_worktree_suppressed(self, tmp_path, hook_env):
        # Worktrees can live anywhere, not just under the repo. The
        # worktree root CLAUDE.md is seeded as an ancestor, so the main
        # repo's identical root copy is suppressed by hash.
        repo = tmp_path / "repo"
        wt = tmp_path / "wt-outside"
        (repo / "sub").mkdir(parents=True)
        (wt / "sub").mkdir(parents=True)
        (repo / "CLAUDE.md").write_text("# shared root\n")
        (wt / "CLAUDE.md").write_text("# shared root\n")
        (repo / "sub" / "CLAUDE.md").write_text("# sub rules\n")
        (wt / "sub" / "CLAUDE.md").write_text("# sub rules\n")

        sid = next_sid("worktree-detached")
        rc, _, stderr = run_hook(build_json(
            tool="Read", sid=sid, cwd=str(wt),
            file_path=str(repo / "sub" / "file.py"),
        ), hook_env)
        assert rc == 0
        assert "CLAUDE.md" not in stderr

    def test_duplicate_of_global_memory_suppressed(self, layout, hook_env):
        # A CLAUDE.md byte-identical to the always-loaded global user
        # memory adds nothing; it must not flag.
        config = Path(hook_env["CLAUDE_CONFIG_DIR"])
        config.mkdir(exist_ok=True)
        (config / "CLAUDE.md").write_text("# sibling\n")

        sid = next_sid("global-dup")
        rc, _, stderr = run_hook(build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        ), hook_env)
        assert rc == 0
        assert "CLAUDE.md" not in stderr


# ---------------------------------------------------------------------------
# Direct access to instruction files (no self-nag)
# ---------------------------------------------------------------------------

class TestDirectAccess:
    def test_read_of_claude_md_not_flagged(self, layout, hook_env):
        sid = next_sid("self-read")
        claude_md = os.path.join(layout["sibling"], "CLAUDE.md")
        rc, _, stderr = run_hook(build_json(
            tool="Read", sid=sid, cwd=layout["project"], file_path=claude_md,
        ), hook_env)
        assert rc == 0
        assert claude_md not in stderr

        # ...and the directory is considered covered afterwards.
        rc, _, _ = run_hook(build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        ), hook_env)
        assert rc == 0

    def test_cat_of_claude_md_not_flagged(self, layout, hook_env):
        sid = next_sid("self-cat")
        claude_md = os.path.join(layout["sibling"], "CLAUDE.md")
        rc, _, stderr = run_hook(build_json(
            tool="Bash", sid=sid, cwd=layout["project"],
            command=f"cat {claude_md}",
        ), hook_env)
        assert rc == 0
        assert claude_md not in stderr

    def test_partial_read_still_flags(self, layout, hook_env):
        # A limited Read doesn't show the whole file, so it doesn't count
        # as having read it.
        sid = next_sid("partial-read")
        claude_md = os.path.join(layout["sibling"], "CLAUDE.md")
        rc, _, stderr = run_hook(build_json(
            tool="Read", sid=sid, cwd=layout["project"], file_path=claude_md,
            extra_input={"limit": 1},
        ), hook_env)
        assert rc == 2
        assert claude_md in stderr

    def test_write_of_claude_md_not_flagged(self, layout, hook_env):
        sid = next_sid("self-write")
        claude_md = os.path.join(layout["sibling"], "CLAUDE.md")
        rc, _, _ = run_hook(build_json(
            tool="Write", sid=sid, cwd=layout["project"], file_path=claude_md,
        ), hook_env)
        assert rc == 0


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

class TestChangeDetection:
    def test_changed_outside_file_reflagged_once(self, layout, hook_env):
        sid = next_sid("changed")
        claude_md = os.path.join(layout["sibling"], "CLAUDE.md")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        )

        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 2

        Path(claude_md).write_text("# sibling, revised\n")
        rc, _, stderr = run_hook(payload, hook_env)
        assert rc == 2
        assert claude_md in stderr
        assert "changed on disk" in stderr

        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 0

    def test_model_edit_does_not_flag_change(self, layout, hook_env):
        sid = next_sid("model-edit")
        claude_md = os.path.join(layout["sibling"], "CLAUDE.md")
        read_payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        )
        rc, _, _ = run_hook(read_payload, hook_env)
        assert rc == 2

        # The model itself rewrites the file: content is in the transcript,
        # so no re-read nudge.
        Path(claude_md).write_text("# sibling, edited by model\n")
        rc, _, _ = run_hook(build_json(
            tool="Edit", sid=sid, cwd=layout["project"], file_path=claude_md,
        ), hook_env)
        assert rc == 0

        rc, _, _ = run_hook(read_payload, hook_env)
        assert rc == 0

    def test_ancestor_change_flagged(self, layout, hook_env):
        sid = next_sid("ancestor-change")
        parent_md = os.path.join(layout["parent"], "CLAUDE.md")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["project"], "file.txt"),
        )
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 0

        Path(parent_md).write_text("# parent, revised\n")
        rc, _, stderr = run_hook(payload, hook_env)
        assert rc == 2
        assert parent_md in stderr
        assert "changed on disk" in stderr

    def test_in_project_subtree_change_flagged(self, layout, hook_env):
        sid = next_sid("subtree-change")
        sub_md = os.path.join(layout["project"], "subdir", "CLAUDE.md")
        Path(sub_md).write_text("# subdir rules\n")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["project"], "subdir", "file.txt"),
        )

        # First access: Claude Code loads it natively; plugin stays silent.
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 0

        Path(sub_md).write_text("# subdir rules, revised\n")
        rc, _, stderr = run_hook(payload, hook_env)
        assert rc == 2
        assert sub_md in stderr
        assert "changed on disk" in stderr

        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 0

    def test_ancestor_created_mid_session_flagged(self, layout, hook_env):
        # The startup walk never saw it, so nothing would ever load it.
        sid = next_sid("new-ancestor")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["project"], "file.txt"),
        )
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 0

        project_md = os.path.join(layout["project"], "CLAUDE.md")
        Path(project_md).write_text("# project rules, created mid-session\n")
        rc, _, stderr = run_hook(payload, hook_env)
        assert rc == 2
        assert project_md in stderr


# ---------------------------------------------------------------------------
# AGENTS.md discovery
# ---------------------------------------------------------------------------

class TestAgentsMd:
    def test_agents_md_flagged_when_no_claude_md(self, layout, hook_env):
        agents = os.path.join(layout["parent"], "agents-only")
        os.makedirs(agents)
        agents_md = os.path.join(agents, "AGENTS.md")
        Path(agents_md).write_text("# agents-only instructions\n")

        sid = next_sid("agents")
        rc, _, stderr = run_hook(build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(agents, "file.txt"),
        ), hook_env)
        assert rc == 2
        assert agents_md in stderr

    def test_claude_md_preferred_over_agents_md(self, layout, hook_env):
        both = os.path.join(layout["parent"], "both-files")
        os.makedirs(both)
        Path(both, "CLAUDE.md").write_text("# both: claude\n")
        Path(both, "AGENTS.md").write_text("# both: agents\n")

        sid = next_sid("both")
        rc, _, stderr = run_hook(build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(both, "file.txt"),
        ), hook_env)
        assert rc == 2
        assert os.path.join(both, "CLAUDE.md") in stderr
        assert os.path.join(both, "AGENTS.md") not in stderr

    def test_agents_md_disabled_via_env(self, layout, hook_env):
        agents = os.path.join(layout["parent"], "agents-off")
        os.makedirs(agents)
        Path(agents, "AGENTS.md").write_text("# agents instructions\n")

        env = {**hook_env, "CLAUDE_MD_DISCOVERY_AGENTS_MD": "0"}
        sid = next_sid("agents-off")
        rc, _, _ = run_hook(build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(agents, "file.txt"),
        ), env)
        assert rc == 0

    def test_project_agents_md_suppresses_identical_copy(self, layout, hook_env):
        # AGENTS.md inside the project (found by the scan) suppresses a
        # byte-identical AGENTS.md outside it.
        Path(layout["project"], "AGENTS.md").write_text("# shared agents\n")
        outside = os.path.join(layout["parent"], "agents-dup")
        os.makedirs(outside)
        Path(outside, "AGENTS.md").write_text("# shared agents\n")

        sid = next_sid("agents-dup")
        rc, _, stderr = run_hook(build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(outside, "file.txt"),
        ), hook_env)
        assert rc == 0
        assert "AGENTS.md" not in stderr


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------

class TestOutputFormat:
    def test_stderr_contains_xml_tags(self, layout, hook_env):
        sid = next_sid("xml")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        )
        _, _, stderr = run_hook(payload, hook_env)
        assert "<claude-md-discovery-extended>" in stderr
        assert "</claude-md-discovery-extended>" in stderr

    def test_stderr_lists_paths(self, layout, hook_env):
        sid = next_sid("paths")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        )
        _, _, stderr = run_hook(payload, hook_env)
        assert os.path.join(layout["sibling"], "CLAUDE.md") in stderr

    def test_stderr_mentions_imports(self, layout, hook_env):
        # Flagged files are read by the model, not natively loaded, so
        # @path imports are not auto-resolved; the message must say so.
        sid = next_sid("imports")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        )
        _, _, stderr = run_hook(payload, hook_env)
        assert "@path imports" in stderr


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_root_path(self, layout, hook_env):
        sid = next_sid("root")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path="/somefile.txt",
        )
        rc, _, _ = run_hook(payload, hook_env)
        assert rc in (0, 2)

    def test_cwd_at_root(self, layout, hook_env):
        sid = next_sid("cwd-root")
        payload = build_json(
            tool="Read", sid=sid, cwd="/",
            file_path=os.path.join(layout["sibling"], "file.txt"),
        )
        rc, _, _ = run_hook(payload, hook_env)
        assert rc in (0, 2)

    def test_target_is_directory(self, layout, hook_env):
        sid = next_sid("dir-target")
        payload = build_json(
            tool="Glob", sid=sid, cwd=layout["project"],
            path=layout["sibling"],
        )
        rc, _, stderr = run_hook(payload, hook_env)
        assert rc == 2
        assert os.path.join(layout["sibling"], "CLAUDE.md") in stderr


# ---------------------------------------------------------------------------
# Diagnostics log
# ---------------------------------------------------------------------------

class TestDiagnosticsLog:
    def test_flag_event_logged(self, layout, hook_env):
        sid = next_sid("log-flag")
        rc, _, _ = run_hook(build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        ), hook_env)
        assert rc == 2

        events = read_log(hook_env, sid)
        flags = [e for e in events if e["event"] == "flag"]
        assert len(flags) == 1
        assert os.path.join(layout["sibling"], "CLAUDE.md") in flags[0]["new"]
        assert flags[0]["tool"] == "Read"

    def test_suppress_event_records_match(self, layout, hook_env):
        sibling2 = os.path.join(layout["parent"], "sibling2")
        os.makedirs(sibling2)
        Path(sibling2, "CLAUDE.md").write_text("# sibling\n")

        sid = next_sid("log-suppress")
        run_hook(build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        ), hook_env)
        run_hook(build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(sibling2, "file.txt"),
        ), hook_env)

        events = read_log(hook_env, sid)
        suppressions = [e for e in events if e["event"] == "suppress"]
        assert len(suppressions) == 1
        assert suppressions[0]["path"] == os.path.join(sibling2, "CLAUDE.md")
        assert suppressions[0]["matched"] == os.path.join(
            layout["sibling"], "CLAUDE.md"
        )

    def test_seed_event_from_session_start(self, layout, hook_env):
        sid = next_sid("log-seed")
        run_script(SESSION_START, {
            "session_id": sid, "cwd": layout["project"], "source": "startup",
        }, hook_env)

        events = read_log(hook_env, sid)
        seeds = [e for e in events if e["event"] == "seed"]
        assert len(seeds) == 1
        assert seeds[0]["trigger"] == "startup"
        assert seeds[0]["scan_method"] in ("git", "walk")
        assert seeds[0]["ancestors"] >= 1  # workspace/CLAUDE.md

    def test_steady_state_logs_nothing(self, layout, hook_env):
        # In-project accesses with no discoveries must not grow the log.
        sid = next_sid("log-quiet")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["project"], "file.txt"),
        )
        run_hook(payload, hook_env)  # lazy seed logs once
        baseline = len(read_log(hook_env, sid))
        for _ in range(3):
            run_hook(payload, hook_env)
        assert len(read_log(hook_env, sid)) == baseline

    def test_swallowed_exception_logged_with_trace(self, layout, hook_env):
        # A malformed tool_input crashes _main; the guard must exit 0 but
        # leave a traceback behind instead of silently eating the bug.
        sid = next_sid("log-error")
        rc, _, _ = run_hook({
            "tool_name": "Read",
            "session_id": sid,
            "cwd": layout["project"],
            "tool_input": "not-a-dict",
        }, hook_env)
        assert rc == 0

        events = read_log(hook_env, sid)
        errors = [e for e in events if e["event"] == "error"]
        assert len(errors) == 1
        assert errors[0]["script"] == "check_claude_md"
        assert "Traceback" in errors[0]["trace"]

    def test_compact_drop_logged(self, layout, hook_env):
        sid = next_sid("log-compact")
        lfile = ledger_file(hook_env, sid)
        lfile.parent.mkdir(parents=True, exist_ok=True)
        lfile.write_text(
            json.dumps({"__seeded__": True}) + "\n"
            + json.dumps({"p": "/lost/CLAUDE.md", "h": "c", "k": "flagged"}) + "\n"
        )
        run_script(SESSION_START, {
            "session_id": sid, "cwd": layout["project"], "source": "compact",
        }, hook_env)

        events = read_log(hook_env, sid)
        drops = [e for e in events if e["event"] == "compact_drop"]
        assert len(drops) == 1
        assert drops[0]["dropped"] == ["/lost/CLAUDE.md"]


# ---------------------------------------------------------------------------
# Ignore list
# ---------------------------------------------------------------------------

class TestIgnoreList:
    def test_ignored_prefix_never_flags(self, layout, hook_env):
        env = {**hook_env, "CLAUDE_MD_DISCOVERY_IGNORE": layout["sibling"]}
        sid = next_sid("ignore")

        rc, _, _ = run_hook(build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        ), env)
        assert rc == 0

        # Other locations are unaffected.
        rc, _, stderr = run_hook(build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["cousin"], "file.txt"),
        ), env)
        assert rc == 2
        assert os.path.join(layout["cousin"], "CLAUDE.md") in stderr

    def test_multiple_prefixes(self, layout, hook_env):
        env = {
            **hook_env,
            "CLAUDE_MD_DISCOVERY_IGNORE": os.pathsep.join(
                [layout["sibling"], layout["cousin"]]
            ),
        }
        sid = next_sid("ignore-multi")
        for target in ("sibling", "cousin"):
            rc, _, _ = run_hook(build_json(
                tool="Read", sid=sid, cwd=layout["project"],
                file_path=os.path.join(layout[target], "file.txt"),
            ), env)
            assert rc == 0

    def test_root_prefix_is_kill_switch(self, layout, hook_env):
        env = {**hook_env, "CLAUDE_MD_DISCOVERY_IGNORE": "/"}
        sid = next_sid("ignore-all")
        rc, _, _ = run_hook(build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        ), env)
        assert rc == 0

    def test_ignored_change_not_flagged(self, layout, hook_env):
        # An ignored ancestor is invisible to change detection too.
        env = {**hook_env, "CLAUDE_MD_DISCOVERY_IGNORE": layout["parent"]}
        sid = next_sid("ignore-change")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["project"], "file.txt"),
        )
        rc, _, _ = run_hook(payload, env)
        assert rc == 0

        Path(layout["parent"], "CLAUDE.md").write_text("# parent, revised\n")
        rc, _, _ = run_hook(payload, env)
        assert rc == 0


# ---------------------------------------------------------------------------
# Real git worktree (exercises the `git ls-files` scan fast path)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
class TestRealGitWorktree:
    @pytest.fixture()
    def git_worktree(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / "some_dir").mkdir(parents=True)
        (repo / "CLAUDE.md").write_text("# root rules\n")
        (repo / "some_dir" / "CLAUDE.md").write_text("# some_dir rules\n")
        (repo / "some_dir" / "app.py").write_text("code\n")
        (repo / ".gitignore").write_text(".worktrees/\n")

        def git(*args):
            subprocess.run(
                ["git", "-C", str(repo), *args],
                check=True, capture_output=True,
            )

        git("init", "-q")
        git("config", "user.email", "t@t")
        git("config", "user.name", "t")
        git("add", "-A")
        git("commit", "-qm", "init")
        git("worktree", "add", "-q", ".worktrees/wt", "-b", "feature")

        return {
            "repo": str(repo),
            "worktree": str(repo / ".worktrees" / "wt"),
        }

    def test_main_repo_duplicates_suppressed(self, git_worktree, hook_env):
        sid = next_sid("git-wt")
        rc, _, _ = run_script(SESSION_START, {
            "session_id": sid, "cwd": git_worktree["worktree"],
            "source": "startup",
        }, hook_env)
        assert rc == 0

        rc, _, stderr = run_hook(build_json(
            tool="Read", sid=sid, cwd=git_worktree["worktree"],
            file_path=os.path.join(git_worktree["repo"], "some_dir", "app.py"),
        ), hook_env)
        assert rc == 0
        assert "CLAUDE.md" not in stderr

    def test_diverged_branch_copy_flags(self, git_worktree, hook_env):
        wt_md = Path(git_worktree["worktree"], "some_dir", "CLAUDE.md")
        wt_md.write_text("# some_dir rules, feature edition\n")

        sid = next_sid("git-wt-diverged")
        rc, _, stderr = run_hook(build_json(
            tool="Read", sid=sid, cwd=git_worktree["worktree"],
            file_path=os.path.join(git_worktree["repo"], "some_dir", "app.py"),
        ), hook_env)
        assert rc == 2
        assert os.path.join(git_worktree["repo"], "some_dir", "CLAUDE.md") in stderr


# ---------------------------------------------------------------------------
# Config-directory exclusion
#
# `${CLAUDE_CONFIG_DIR:-~/.claude}` holds Claude Code's own config and
# installed plugins. Its `CLAUDE.md` is the global user memory that Claude
# Code always loads at startup, so discovery must never resurface anything
# inside that tree -- otherwise touching any config/plugin file (which
# happens constantly) nags the model to re-read files already in context.
# ---------------------------------------------------------------------------

@pytest.fixture()
def config_layout(tmp_path, hook_env):
    """Create a project cwd and populate the pinned Claude config dir.

    tmp/workspace/project/                 (cwd, outside config)
    tmp/workspace/sibling/                 CLAUDE.md (legit discovery)
    tmp/claude-config/                     CLAUDE.md (global user memory)
    tmp/claude-config/plugins/foo/         CLAUDE.md (plugin ships its own)
    tmp/claude-config/plugins/foo/hooks/
    """
    project = tmp_path / "workspace" / "project"
    sibling = tmp_path / "workspace" / "sibling"
    config = Path(hook_env["CLAUDE_CONFIG_DIR"])
    plugin_hooks = config / "plugins" / "foo" / "hooks"

    project.mkdir(parents=True)
    sibling.mkdir(parents=True)
    plugin_hooks.mkdir(parents=True)

    (sibling / "CLAUDE.md").write_text("# sibling\n")
    (config / "CLAUDE.md").write_text("# global user memory\n")
    (config / "plugins" / "foo" / "CLAUDE.md").write_text("# plugin repo\n")

    return {
        "project": str(project),
        "sibling": str(sibling),
        "config": str(config),
        "plugin": str(config / "plugins" / "foo"),
        "plugin_hooks": str(plugin_hooks),
    }


class TestConfigDirExclusion:
    def test_global_memory_not_reported(self, config_layout, hook_env):
        # Reading a config file (e.g. settings.json) must not resurface
        # the global-memory CLAUDE.md sitting beside it.
        sid = next_sid("cfg-global")
        payload = build_json(
            tool="Read", sid=sid, cwd=config_layout["project"],
            file_path=os.path.join(config_layout["config"], "settings.json"),
        )
        rc, _, stderr = run_hook(payload, hook_env)
        assert rc == 0
        assert "CLAUDE.md" not in stderr

    def test_plugin_claude_md_under_config_not_reported(self, config_layout, hook_env):
        # A plugin that ships its own CLAUDE.md inside the config tree
        # must not be flagged when the model reads that plugin's files.
        sid = next_sid("cfg-plugin")
        payload = build_json(
            tool="Read", sid=sid, cwd=config_layout["project"],
            file_path=os.path.join(config_layout["plugin_hooks"], "script.py"),
        )
        rc, _, stderr = run_hook(payload, hook_env)
        assert rc == 0
        assert "CLAUDE.md" not in stderr

    def test_bash_touching_config_path_not_reported(self, config_layout, hook_env):
        # The common real-world trigger: a Bash command that merely names
        # a path inside the config dir (find/grep/ls over ~/.claude).
        sid = next_sid("cfg-bash")
        payload = build_json(
            tool="Bash", sid=sid, cwd=config_layout["project"],
            command=f"find {config_layout['config']} -name script.py",
        )
        rc, _, stderr = run_hook(payload, hook_env)
        assert rc == 0
        assert "CLAUDE.md" not in stderr

    def test_sibling_still_discovered_with_config_dir_set(self, config_layout, hook_env):
        # Guard against over-exclusion: a genuine sibling outside the
        # config tree must still be discovered while CLAUDE_CONFIG_DIR is set.
        sid = next_sid("cfg-sibling-ok")
        payload = build_json(
            tool="Read", sid=sid, cwd=config_layout["project"],
            file_path=os.path.join(config_layout["sibling"], "file.txt"),
        )
        rc, _, stderr = run_hook(payload, hook_env)
        assert rc == 2
        assert os.path.join(config_layout["sibling"], "CLAUDE.md") in stderr


# ---------------------------------------------------------------------------
# SessionStart lifecycle
# ---------------------------------------------------------------------------

class TestSessionStart:
    def test_seeds_ledger(self, layout, hook_env):
        sid = next_sid("ss-seed")
        rc, stdout, _ = run_script(SESSION_START, {
            "session_id": sid, "cwd": layout["project"], "source": "startup",
        }, hook_env)
        assert rc == 0
        assert stdout == ""

        entries = read_ledger(hook_env, sid)
        parent_md = os.path.realpath(os.path.join(layout["parent"], "CLAUDE.md"))
        assert parent_md in entries
        assert entries[parent_md]["k"] == "context"

    def test_scan_records_project_files_as_equiv(self, layout, hook_env):
        sub_md = os.path.join(layout["project"], "subdir", "CLAUDE.md")
        Path(sub_md).write_text("# subdir rules\n")

        sid = next_sid("ss-scan")
        run_script(SESSION_START, {
            "session_id": sid, "cwd": layout["project"], "source": "startup",
        }, hook_env)

        entries = read_ledger(hook_env, sid)
        assert os.path.realpath(sub_md) in entries
        assert entries[os.path.realpath(sub_md)]["k"] == "equiv"

    def test_clear_resets_ledger(self, layout, hook_env):
        sid = next_sid("ss-clear")
        lfile = ledger_file(hook_env, sid)
        lfile.parent.mkdir(parents=True, exist_ok=True)
        lfile.write_text(
            json.dumps({"__seeded__": True}) + "\n"
            + json.dumps({"p": "/old/CLAUDE.md", "h": "stale", "k": "flagged"}) + "\n"
        )

        rc, _, _ = run_script(SESSION_START, {
            "session_id": sid, "cwd": layout["project"], "source": "clear",
        }, hook_env)
        assert rc == 0

        entries = read_ledger(hook_env, sid)
        assert "/old/CLAUDE.md" not in entries
        # Re-seeded fresh from disk.
        parent_md = os.path.realpath(os.path.join(layout["parent"], "CLAUDE.md"))
        assert parent_md in entries

    def test_compact_drops_flagged_keeps_context(self, layout, hook_env):
        sid = next_sid("ss-compact")
        lfile = ledger_file(hook_env, sid)
        lfile.parent.mkdir(parents=True, exist_ok=True)
        lfile.write_text(
            json.dumps({"__seeded__": True}) + "\n"
            + json.dumps({"p": "/kept/CLAUDE.md", "h": "a", "k": "context"}) + "\n"
            + json.dumps({"p": "/dupe/CLAUDE.md", "h": "b", "k": "equiv"}) + "\n"
            + json.dumps({"p": "/lost/CLAUDE.md", "h": "c", "k": "flagged"}) + "\n"
        )

        rc, _, _ = run_script(SESSION_START, {
            "session_id": sid, "cwd": layout["project"], "source": "compact",
        }, hook_env)
        assert rc == 0

        entries = read_ledger(hook_env, sid)
        assert "/kept/CLAUDE.md" in entries
        assert "/dupe/CLAUDE.md" in entries
        assert "/lost/CLAUDE.md" not in entries

    def test_flagged_file_reflags_after_compact(self, layout, hook_env):
        # Full loop: flag -> compact -> the transcript-carried content is
        # gone, so the same file flags again on next access.
        sid = next_sid("ss-compact-loop")
        payload = build_json(
            tool="Read", sid=sid, cwd=layout["project"],
            file_path=os.path.join(layout["sibling"], "file.txt"),
        )
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 2
        rc, _, _ = run_hook(payload, hook_env)
        assert rc == 0

        run_script(SESSION_START, {
            "session_id": sid, "cwd": layout["project"], "source": "compact",
        }, hook_env)

        rc, _, stderr = run_hook(payload, hook_env)
        assert rc == 2
        assert os.path.join(layout["sibling"], "CLAUDE.md") in stderr

    def test_gc_removes_stale_ledgers(self, layout, hook_env, tmp_path):
        state = Path(hook_env["CLAUDE_MD_DISCOVERY_STATE_DIR"])
        state.mkdir(parents=True, exist_ok=True)
        stale = state / "ancient.jsonl"
        stale.write_text("{}\n")
        old = time.time() - 40 * 86400
        os.utime(stale, (old, old))
        fresh = state / "fresh.jsonl"
        fresh.write_text("{}\n")

        sid = next_sid("ss-gc")
        run_script(SESSION_START, {
            "session_id": sid, "cwd": layout["project"], "source": "startup",
        }, hook_env)

        assert not stale.exists()
        assert fresh.exists()

    def test_gc_removes_legacy_tmpdir_files(self, layout, hook_env, tmp_path):
        fake_tmp = tmp_path / "faketmp"
        fake_tmp.mkdir()
        legacy = fake_tmp / "claude-md-seen-oldsession"
        legacy.write_text("/some/CLAUDE.md\n")
        old = time.time() - 8 * 86400
        os.utime(legacy, (old, old))

        env = {**hook_env, "TMPDIR": str(fake_tmp)}
        sid = next_sid("ss-legacy")
        run_script(SESSION_START, {
            "session_id": sid, "cwd": layout["project"], "source": "startup",
        }, env)

        assert not legacy.exists()

    def test_missing_fields_exit_0(self, hook_env):
        rc, _, _ = run_script(SESSION_START, {}, hook_env)
        assert rc == 0


# ---------------------------------------------------------------------------
# SessionEnd lifecycle
# ---------------------------------------------------------------------------

class TestSessionEnd:
    def _make_ledger(self, hook_env, sid) -> Path:
        lfile = ledger_file(hook_env, sid)
        lfile.parent.mkdir(parents=True, exist_ok=True)
        lfile.write_text(json.dumps({"__seeded__": True}) + "\n")
        return lfile

    def test_clear_deletes_ledger(self, hook_env):
        sid = next_sid("se-clear")
        lfile = self._make_ledger(hook_env, sid)
        rc, _, _ = run_script(SESSION_END, {
            "session_id": sid, "reason": "clear",
        }, hook_env)
        assert rc == 0
        assert not lfile.exists()

    @pytest.mark.parametrize("reason", ["exit", "logout", "other", ""])
    def test_other_reasons_keep_ledger(self, hook_env, reason):
        # The session might be resumed with the same id; state must survive.
        sid = next_sid("se-keep")
        lfile = self._make_ledger(hook_env, sid)
        rc, _, _ = run_script(SESSION_END, {
            "session_id": sid, "reason": reason,
        }, hook_env)
        assert rc == 0
        assert lfile.exists()

    def test_missing_session_id_exits_0(self, hook_env):
        rc, _, _ = run_script(SESSION_END, {"reason": "clear"}, hook_env)
        assert rc == 0
