#!/usr/bin/env bash
#
# Deterministic test for the fix-docstrings LangChain hook
# (plugins/fix-docstrings/hooks/scripts/langchain_tool_context.py).
#
# Feeds crafted hook payloads to the script and asserts the injected context,
# with no live model. Covers parser-enabled tool detection, invocation-scoped
# state, cleanup, and both skill activation routes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$REPO_ROOT/plugins/fix-docstrings"
SCRIPT="$ROOT/hooks/scripts/langchain_tool_context.py"
HOOKS="$ROOT/hooks/hooks.json"
MANIFEST="$ROOT/.claude-plugin/plugin.json"
MARKETPLACE="$REPO_ROOT/.claude-plugin/marketplace.json"
REFERENCE="$ROOT/skills/fix-docstrings/references/langchain-tool-docstrings.md"
PLUGIN_README="$ROOT/README.md"
PYTHON=(uv run --no-project python)

FIX="$(mktemp -d)"
trap 'rm -rf "$FIX"' EXIT

mkdir -p "$FIX/proj/sub" "$FIX/state"
PARSED_TOOL_SRC=$'from langchain_core.tools import tool\n\n@tool(parse_docstring=True)\ndef act(x: str) -> str:\n    """Act.\n\n    Args:\n        x: Value.\n    """\n    return x\n'
DEFAULT_TOOL_SRC=$'from langchain_core.tools import tool\n\n@tool\ndef act(x: str) -> str:\n    """Act."""\n    return x\n'
ALIASED_TOOL_SRC=$'from langchain_core.tools import tool as lc_tool\n\n@lc_tool(parse_docstring=True)\ndef act(x: str) -> str:\n    """Act."""\n    return x\n'
DIRECT_ALIASED_TOOL_SRC=$'from langchain_core.tools import tool as lc_tool\n\ndef act(x: str) -> str:\n    """Act."""\n    return x\n\nACT = lc_tool(act, parse_docstring=True)\n'
STRUCTURED_TOOL_SRC=$'from langchain_core.tools import StructuredTool\n\ndef act(x: str) -> str:\n    """Act."""\n    return x\n\nACT = StructuredTool.from_function(act, parse_docstring=True)\n'
UNRELATED_DECORATOR_SRC=$'from project_tools import custom\n\n@custom(parse_docstring=True)\ndef act(x: str) -> str:\n    """Act."""\n    return x\n'
FOREIGN_TOOL_SRC=$'from project_tools import tool\n\n@tool(parse_docstring=True)\ndef act(x: str) -> str:\n    """Act."""\n    return x\n'
UNRELATED_FACTORY_SRC=$'from project_tools import Other\n\ndef act(x: str) -> str:\n    """Act."""\n    return x\n\nACT = Other.from_function(act, parse_docstring=True)\n'
printf '%s' "$PARSED_TOOL_SRC" > "$FIX/proj/a_tool.py"
printf '%s' "$ALIASED_TOOL_SRC" > "$FIX/proj/sub/aliased_tool.py"
printf '%s' "$DIRECT_ALIASED_TOOL_SRC" > "$FIX/proj/sub/direct_aliased_tool.py"
printf '%s' "$STRUCTURED_TOOL_SRC" > "$FIX/proj/structured_tool.py"
printf '%s' "$DEFAULT_TOOL_SRC" > "$FIX/proj/default_tool.py"
printf '%s' "$UNRELATED_DECORATOR_SRC" > "$FIX/proj/unrelated_decorator.py"
printf '%s' "$FOREIGN_TOOL_SRC" > "$FIX/proj/foreign_tool.py"
printf '%s' "$UNRELATED_FACTORY_SRC" > "$FIX/proj/unrelated_factory.py"
printf '%s' "$PARSED_TOOL_SRC" > "$FIX/outside_tool.py"
printf 'def plain():\n    return 1\n' > "$FIX/proj/plain.py"
printf 'configure(parse_docstring=True)\n' > "$FIX/proj/unrelated.py"

PASS=0; FAIL=0
check() { # label expected actual
  if [ "$2" = "$3" ]; then printf '  ok   %s -> %s\n' "$1" "$3"; PASS=$((PASS+1))
  else printf '  FAIL %s: expected=%s actual=%s\n' "$1" "$2" "$3"; FAIL=$((FAIL+1)); fi
}
assert_lists() { # label needle haystack  (haystack must contain needle)
  if printf '%s' "$3" | grep -qF "$2"; then printf '  ok   %s lists %s\n' "$1" "$2"; PASS=$((PASS+1))
  else printf '  FAIL %s: missing %s\n' "$1" "$2"; FAIL=$((FAIL+1)); fi
}
refute_lists() { # label needle haystack  (haystack must NOT contain needle)
  if printf '%s' "$3" | grep -qF "$2"; then printf '  FAIL %s: should not list %s\n' "$1" "$2"; FAIL=$((FAIL+1))
  else printf '  ok   %s omits %s\n' "$1" "$2"; PASS=$((PASS+1)); fi
}

mk_expansion() { "${PYTHON[@]}" -c 'import json,sys;print(json.dumps({"session_id":sys.argv[1],"hook_event_name":"UserPromptExpansion","command_name":"fix-docstrings","command_args":sys.argv[2],"cwd":sys.argv[3]}))' "$1" "$2" "$3"; }
mk_skill()     { "${PYTHON[@]}" -c 'import json,sys;print(json.dumps({"session_id":sys.argv[1],"hook_event_name":"PostToolUse","tool_name":"Skill","tool_input":{"skill":"fix-docstrings"}}))' "$1"; }
mk_read()      { "${PYTHON[@]}" -c 'import json,sys;print(json.dumps({"session_id":sys.argv[1],"hook_event_name":"PostToolUse","tool_name":"Read","tool_input":{"file_path":sys.argv[2]}}))' "$1" "$2"; }

trig()    { printf '%s' "$1" | TMPDIR="$FIX/state" "${PYTHON[@]}" "$SCRIPT" trigger "$ROOT"; }
detect()  { printf '%s' "$(mk_read "$1" "$2")" | TMPDIR="$FIX/state" "${PYTHON[@]}" "$SCRIPT" detect "$ROOT"; }
cleanup() { printf '%s' "$1" | TMPDIR="$FIX/state" "${PYTHON[@]}" "$SCRIPT" cleanup "$ROOT"; }

# Program passed via -c so the piped hook output stays on stdin (a heredoc here
# would replace stdin with the script text).
classify() {
  "${PYTHON[@]}" -c '
import json,sys
raw=sys.stdin.read().strip()
if not raw: print("SILENT"); sys.exit()
try:
    h=json.loads(raw)["hookSpecificOutput"]; ctx=h["additionalContext"]; ev=h["hookEventName"]
except Exception: print("MALFORMED"); sys.exit()
if ev=="UserPromptExpansion" and "parse_docstring=True" in ctx: print("UPFRONT")
elif ev=="PostToolUse" and "parse_docstring=True" in ctx: print("SAFE")
else: print("OTHER")
'
}

echo "== Scenario A: directory target, upfront scan =="
S="hooktest-A-$$"
OUT="$(trig "$(mk_expansion "$S" "please fix @$FIX/proj/ now" "$FIX")")"
check     "A dir-trigger classification" UPFRONT "$(printf '%s' "$OUT" | classify)"
assert_lists "A" "$FIX/proj/a_tool.py" "$OUT"
assert_lists "A" "$FIX/proj/sub/aliased_tool.py" "$OUT"
assert_lists "A" "$FIX/proj/sub/direct_aliased_tool.py" "$OUT"
assert_lists "A" "$FIX/proj/structured_tool.py" "$OUT"
refute_lists "A" "$FIX/proj/default_tool.py" "$OUT"
refute_lists "A" "$FIX/proj/plain.py" "$OUT"
refute_lists "A" "$FIX/proj/unrelated.py" "$OUT"
refute_lists "A" "$FIX/proj/unrelated_decorator.py" "$OUT"
refute_lists "A" "$FIX/proj/foreign_tool.py" "$OUT"
refute_lists "A" "$FIX/proj/unrelated_factory.py" "$OUT"
check     "A read of listed file is silent" SILENT "$(detect "$S" "$FIX/proj/a_tool.py" | classify)"
check     "A read of outside parsed tool is self-contained" SAFE "$(detect "$S" "$FIX/outside_tool.py" | classify)"
check     "A read of default @tool file is silent" SILENT "$(detect "$S" "$FIX/proj/default_tool.py" | classify)"
check     "A read of plain file is silent" SILENT "$(detect "$S" "$FIX/proj/plain.py" | classify)"

echo "== Scenario B: single-file target, upfront scan =="
S="hooktest-B-$$"
OUT="$(trig "$(mk_expansion "$S" "@$FIX/proj/a_tool.py" "$FIX")")"
check     "B file-trigger classification" UPFRONT "$(printf '%s' "$OUT" | classify)"
assert_lists "B" "$FIX/proj/a_tool.py" "$OUT"
refute_lists "B" "$FIX/proj/sub/aliased_tool.py" "$OUT"
check     "B read of listed file is silent" SILENT "$(detect "$S" "$FIX/proj/a_tool.py" | classify)"

echo "== Scenario C: no target path -> Read-detector fallback =="
S="hooktest-C-$$"
check     "C trigger with no path is silent" SILENT "$(trig "$(mk_expansion "$S" "just fix the docstrings" "$FIX")" | classify)"
OUT="$(detect "$S" "$FIX/proj/a_tool.py")"
check     "C first parsed-tool read is self-contained" SAFE "$(printf '%s' "$OUT" | classify)"
assert_lists "C first reminder" "langchain-tool-docstrings.md" "$OUT"
assert_lists "C first reminder" "colon-bearing" "$OUT"
assert_lists "C first reminder" "signature annotation" "$OUT"
OUT="$(detect "$S" "$FIX/proj/sub/aliased_tool.py")"
check     "C second parsed-tool read is self-contained" SAFE "$(printf '%s' "$OUT" | classify)"
assert_lists "C second reminder" "langchain-tool-docstrings.md" "$OUT"
assert_lists "C second reminder" "colon-bearing" "$OUT"
check     "C re-read of first file is silent" SILENT "$(detect "$S" "$FIX/proj/a_tool.py" | classify)"

echo "== Scenario D: model (Skill-tool) invocation -> fallback =="
S="hooktest-D-$$"
check     "D skill trigger is silent (no target)" SILENT "$(trig "$(mk_skill "$S")" | classify)"
check     "D first parsed-tool read is self-contained" SAFE "$(detect "$S" "$FIX/proj/a_tool.py" | classify)"

echo "== Scenario E: state is scoped to one invocation =="
S="hooktest-E-$$"
trig "$(mk_skill "$S")" >/dev/null
check     "E first invocation detects file" SAFE "$(detect "$S" "$FIX/proj/a_tool.py" | classify)"
trig "$(mk_skill "$S")" >/dev/null
check     "E next invocation detects same file again" SAFE "$(detect "$S" "$FIX/proj/a_tool.py" | classify)"
cleanup "$(mk_skill "$S")" >/dev/null
check     "E cleanup disarms later reads" SILENT "$(detect "$S" "$FIX/outside_tool.py" | classify)"

echo "== Static hook and reference contracts =="
if "${PYTHON[@]}" -c 'import json,sys; hooks=json.load(open(sys.argv[1]))["hooks"]; assert "Stop" in hooks and "SessionEnd" in hooks' "$HOOKS"; then
  printf '  ok   cleanup is registered for Stop and SessionEnd\n'; PASS=$((PASS+1))
else
  printf '  FAIL cleanup is not registered for Stop and SessionEnd\n'; FAIL=$((FAIL+1))
fi
if "${PYTHON[@]}" -c '
import json, sys
manifest = json.load(open(sys.argv[1]))
marketplace = json.load(open(sys.argv[2]))
entry = next(item for item in marketplace["plugins"] if item["name"] == "fix-docstrings")
assert manifest["version"] == entry["version"] == "0.1.1"
assert "parse_docstring" in manifest["description"]
assert "parse_docstring" in entry["description"]
' "$MANIFEST" "$MARKETPLACE"; then
  printf '  ok   release manifests expose fix-docstrings 0.1.1\n'; PASS=$((PASS+1))
else
  printf '  FAIL release manifests are stale or disagree\n'; FAIL=$((FAIL+1))
fi
REF_TEXT="$(<"$REFERENCE")"
assert_lists "reference" 'parse_docstring=False' "$REF_TEXT"
assert_lists "reference" 'parenthesized types are accepted' "$REF_TEXT"
assert_lists "reference" 'colon-bearing continuation' "$REF_TEXT"
assert_lists "reference" 'requires a signature annotation' "$REF_TEXT"
refute_lists "reference" 'risks corrupting parsed output' "$REF_TEXT"
refute_lists "reference" 'include it when' "$REF_TEXT"
README_TEXT="$(<"$PLUGIN_README")"
refute_lists "plugin README" 're-exported decorators' "$README_TEXT"

echo
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
