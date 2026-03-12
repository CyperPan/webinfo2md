#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

env PYTHONPATH=src python3 -m webinfo2md \
  --url "https://example.com/interview-post" \
  --template interview-general \
  --prompt "提取所有面试问题，整理为八股文格式，补充标准答案" \
  --dry-run \
  --output demo-output.md
