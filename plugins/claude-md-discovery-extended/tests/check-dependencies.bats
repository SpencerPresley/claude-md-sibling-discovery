#!/usr/bin/env bats

load test_helper

DEPS_SCRIPT="${SCRIPT_DIR}/check-dependencies.sh"

# To simulate python3 missing, we create a wrapper script that overrides
# PATH before sourcing the real script. We can't just set PATH="/dev/null"
# because bash itself needs to resolve builtins and the script uses
# 'command -v'.
setup() {
  TEST_DIR=$(mktemp -d)

  # Create a wrapper that puts an empty dir first in PATH,
  # hiding python3 but keeping bash builtins functional.
  EMPTY_BIN="${TEST_DIR}/empty-bin"
  mkdir -p "${EMPTY_BIN}"

  cat > "${TEST_DIR}/no-python-wrapper.sh" <<WRAPPER
#!/bin/bash
export PATH="${EMPTY_BIN}"
source "${DEPS_SCRIPT}"
WRAPPER
  chmod +x "${TEST_DIR}/no-python-wrapper.sh"
}

teardown() {
  rm -rf "${TEST_DIR}"
}

@test "exits 0 when python3 is available" {
  local exit_code=0
  bash "${DEPS_SCRIPT}" 2>/dev/null || exit_code=$?
  [[ "${exit_code}" -eq 0 ]]
}

@test "exits 2 when python3 is not available" {
  local exit_code=0
  bash "${TEST_DIR}/no-python-wrapper.sh" 2>/dev/null || exit_code=$?
  [[ "${exit_code}" -eq 2 ]]
}

@test "stderr contains install instructions when python3 missing" {
  local stderr_out=""
  stderr_out=$(bash "${TEST_DIR}/no-python-wrapper.sh" 2>&1 >/dev/null) || true
  [[ "${stderr_out}" == *"requires python3"* ]]
  [[ "${stderr_out}" == *"apt-get install python3"* ]]
}

@test "no stderr output when python3 is available" {
  local stderr_out=""
  stderr_out=$(bash "${DEPS_SCRIPT}" 2>&1 >/dev/null) || true
  [[ -z "${stderr_out}" ]]
}
