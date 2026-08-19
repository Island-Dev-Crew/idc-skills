#!/usr/bin/env bash
# Run the red-before-green integrity matrix in isolated temporary repositories.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

python3 -m unittest -v tests.test_skill_integrity
printf '\nRESULT skill-integrity matrix=green\n'
