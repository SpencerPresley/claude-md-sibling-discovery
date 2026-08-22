#!/usr/bin/env bash
# Preflight for the pyrefly LSP server.
#
# Exit 2 with a message on stderr renders a hook error notice in the transcript
# (Claude Code >= 2.1.199). The user sees it; the model does not, so a warning
# costs no context. Exit 0 silently on the happy path — SessionStart stdout is
# injected into context, so success must print nothing at all.
#
# Ordering is latency-driven: the shell builtin runs always, the git probes only
# in a linked worktree, and nothing here ever touches the network.

set -uo pipefail

problems=()

# 1. uv on PATH. Without it the server cannot spawn at all; Claude Code reports
#    `Executable not found in $PATH` in the /plugin Errors tab, which is easy to
#    miss because everything else keeps working.
if ! command -v uv >/dev/null 2>&1; then
  problems+=("uv is not on PATH, so \`uvx pyrefly ... lsp\` cannot start and Python code intelligence will be silently absent. Install: https://docs.astral.sh/uv/getting-started/installation/")
fi

# 2. Gitignored working copy. Pyrefly's ignore-file search walks UP from the
#    project root; if an ancestor .gitignore or .git/info/exclude matches this
#    checkout, workspace-wide operations (findReferences, workspaceSymbol)
#    return small, plausible, WRONG answers instead of erroring, while per-file
#    diagnostics and hover keep working — so nothing looks broken.
#
#    Only linked worktrees can hit this, and `.git` is a file rather than a
#    directory in exactly that case, so the git calls below are skipped
#    entirely in an ordinary clone.
if [[ -f .git ]]; then
  # Read .git/info/exclude directly rather than asking `git check-ignore`.
  # check-ignore only reports the HIGHEST-precedence match, and a main
  # checkout's .gitignore outranks info/exclude — so it reports the .gitignore
  # rule, which is harmless here (pyrefly resolves the worktree's own .gitignore
  # relative to the worktree root, where those patterns don't match) and hides
  # the info/exclude rule, which is the one that actually breaks indexing.
  #
  # The linked-worktree .git file holds the gitdir path, so this needs no
  # subprocess at all: `gitdir: /path/to/main/.git/worktrees/<name>`.
  _gitdir=$(<.git) || _gitdir=""
  _gitdir=${_gitdir#gitdir: }
  if [[ ${_gitdir} == */worktrees/* ]]; then
    _common=${_gitdir%/worktrees/*}
    _exclude="${_common}/info/exclude"
    _rel=${PWD#"${_common%/.git}/"}
    if [[ -f ${_exclude} ]]; then
      while IFS= read -r _line || [[ -n ${_line} ]]; do
        [[ -z ${_line} || ${_line} == '#'* || ${_line} == '!'* ]] && continue
        _pat=${_line#/}; _pat=${_pat#\*\*/}; _pat=${_pat%/}
        [[ -z ${_pat} || ${_pat} == *'*'* ]] && continue
        if [[ "/${_rel}/" == *"/${_pat}/"* ]]; then
          problems+=("this worktree is matched by \`${_line}\` in ${_exclude}, so pyrefly indexes only the file you have open — findReferences and workspaceSymbol under-report with no error. Delete that line.")
          break
        fi
      done < "${_exclude}"
    fi
  fi
fi

if ((${#problems[@]})); then
  {
    echo "pyrefly-lsp preflight:"
    for p in "${problems[@]}"; do echo "  - ${p}"; done
  } >&2
  exit 2
fi

exit 0
