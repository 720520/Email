#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TOOLS_DIR="$PROJECT_ROOT/.tools"
LOCAL_PNPM_DIR="$TOOLS_DIR/pnpm"
LOCAL_PNPM="$LOCAL_PNPM_DIR/node_modules/.bin/pnpm"
PNPM_VERSION="${FUND_NAV_PNPM_VERSION:-11.24.0}"

pnpm_major() {
  "$1" --version 2>/dev/null | awk -F. 'NR == 1 {print $1}'
}

# Prefer a working system pnpm 11. This deliberately bypasses Corepack: some
# distro Corepack builds fail to launch pnpm under Node 22 with
# ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING.
if command -v pnpm >/dev/null 2>&1; then
  system_pnpm="$(command -v pnpm)"
  if [[ "$(pnpm_major "$system_pnpm")" == "11" ]]; then
    exec "$system_pnpm" "$@"
  fi
fi

if [[ ! -x "$LOCAL_PNPM" ]] || [[ "$(pnpm_major "$LOCAL_PNPM")" != "11" ]]; then
  command -v npm >/dev/null 2>&1 || {
    printf '缺少可用的 pnpm 11 和 npm，请安装 Node.js 22/24 完整版。\n' >&2
    exit 1
  }
  printf '未找到可用的系统 pnpm 11，正在项目内安装 pnpm %s...\n' "$PNPM_VERSION" >&2
  mkdir -p "$LOCAL_PNPM_DIR"
  npm install --prefix "$LOCAL_PNPM_DIR" --cache "$PROJECT_ROOT/.cache/npm" \
    --no-save --no-audit --no-fund \
    "pnpm@$PNPM_VERSION"
fi

exec "$LOCAL_PNPM" "$@"
