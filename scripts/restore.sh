#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR=""
DATA_DIR="${FUND_NAV_DATA_DIR:-$PROJECT_ROOT/data}"
FORCE=0

die() { printf '恢复失败：%s\n' "$1" >&2; exit 1; }

usage() {
  cat <<'EOF'
用法：scripts/restore.sh --backup DIR [--data-dir DIR] [--force]

先校验 SHA-256 清单，再恢复数据库及文件。目标目录非空时必须传 --force；
原目录会被保留为同级的 .pre-restore-* 回滚副本，不会直接删除。
恢复前必须停止后端和 Worker。
EOF
}

while (($#)); do
  case "$1" in
    --backup) (($# >= 2)) || die "--backup 需要目录"; BACKUP_DIR="$2"; shift ;;
    --data-dir) (($# >= 2)) || die "--data-dir 需要目录"; DATA_DIR="$2"; shift ;;
    --force) FORCE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "未知选项：$1" ;;
  esac
  shift
done

[[ -n "$BACKUP_DIR" ]] || die "必须指定 --backup"
BACKUP_DIR="$(realpath -m "$BACKUP_DIR")"
DATA_DIR="$(realpath -m "$DATA_DIR")"
[[ -d "$BACKUP_DIR/data" && -f "$BACKUP_DIR/SHA256SUMS" ]] \
  || die "备份结构不完整：$BACKUP_DIR"
(cd "$BACKUP_DIR" && sha256sum --check --strict SHA256SUMS >/dev/null) \
  || die "SHA-256 校验失败，拒绝恢复"

if [[ -d "$DATA_DIR" && -n "$(find "$DATA_DIR" -mindepth 1 -print -quit)" ]]; then
  ((FORCE)) || die "目标数据目录非空；确认服务已停止后使用 --force"
  rollback="${DATA_DIR}.pre-restore-$(date +%Y%m%d-%H%M%S)"
  mv "$DATA_DIR" "$rollback"
  printf '原数据已保留：%s\n' "$rollback"
elif [[ -e "$DATA_DIR" && ! -d "$DATA_DIR" ]]; then
  die "目标数据路径不是目录：$DATA_DIR"
fi

mkdir -p "$(dirname -- "$DATA_DIR")"
cp -a "$BACKUP_DIR/data" "$DATA_DIR"
printf '数据恢复完成：%s\n' "$DATA_DIR"
printf '备份代码版本：%s\n' "$(cat "$BACKUP_DIR/source-commit.txt" 2>/dev/null || printf unknown)"
