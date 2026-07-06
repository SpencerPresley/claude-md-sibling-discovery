#!/bin/bash
# Warn once at session start if required dependencies are not installed.
set -Eeuo pipefail

command -v python3 &>/dev/null && exit 0

{
  printf '<claude-md-discovery-extended>\n'
  printf 'The claude-md-discovery-extended plugin requires python3 but it is not installed.\n'
  printf 'The plugin will not function until it is available.\n'
  printf 'Python 3 is typically pre-installed on macOS and most Linux distributions.\n'
  printf 'Install: brew install python3 (macOS) or apt-get install python3 (Linux)\n'
  printf '</claude-md-discovery-extended>\n'
} >&2
exit 2
