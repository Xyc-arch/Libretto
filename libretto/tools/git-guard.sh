#!/bin/sh
# libretto frozen-core guard — installed as .git/hooks/pre-commit and pre-merge-commit.
# Fails the commit/merge if the core guard-tests fail OR the frozen validated core changed.
set -e
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
echo "[guard] core guard-tests..."
PYTHONPATH="$ROOT" python3 -m libretto.tests.test_core >/dev/null
echo "[guard] frozen-core hash check..."
PYTHONPATH="$ROOT" python3 libretto/tools/check_frozen_core.py
echo "[guard] OK — frozen core intact, guard-tests pass."
