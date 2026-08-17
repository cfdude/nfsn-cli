#!/usr/bin/env bash
# Point git at the tracked hooks in .githooks/.
set -e
REPO_ROOT="$(git rev-parse --show-toplevel)"
git -C "$REPO_ROOT" config core.hooksPath .githooks
echo "core.hooksPath set to .githooks"
echo "Hooks active:"
ls -1 "$REPO_ROOT/.githooks"
