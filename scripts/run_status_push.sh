#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REPORT_PATH="${ROOT_DIR}/assets/latest_update.md"

cd "${ROOT_DIR}"
if [[ -f "${REPORT_PATH}" ]]; then
  cat "${REPORT_PATH}"
else
  echo "⚠️ 尚无缓存报告。请先运行更新任务生成。"
fi
