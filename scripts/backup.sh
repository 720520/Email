#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="${FUND_NAV_DATA_DIR:-$PROJECT_ROOT/data}"
BACKUP_ROOT="${FUND_NAV_BACKUP_DIR:-$PROJECT_ROOT/backups}"
LABEL="$(date +%Y%m%d-%H%M%S)"

die() { printf '备份失败：%s\n' "$1" >&2; exit 1; }

usage() {
  cat <<'EOF'
用法：scripts/backup.sh [--data-dir DIR] [--backup-root DIR] [--label NAME]

创建数据库、归档文件和本地配置的一致目录副本，并生成 SHA-256 校验清单。
运行前应停止应用写入；正式部署脚本会在停止服务前继续使用自身的升级前快照。
EOF
}

while (($#)); do
  case "$1" in
    --data-dir) (($# >= 2)) || die "--data-dir 需要目录"; DATA_DIR="$2"; shift ;;
    --backup-root) (($# >= 2)) || die "--backup-root 需要目录"; BACKUP_ROOT="$2"; shift ;;
    --label) (($# >= 2)) || die "--label 需要名称"; LABEL="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "未知选项：$1" ;;
  esac
  shift
done

[[ "$LABEL" =~ ^[A-Za-z0-9._-]+$ ]] || die "备份名称只能包含字母、数字、点、下划线和连字符"
DATA_DIR="$(realpath -m "$DATA_DIR")"
BACKUP_ROOT="$(realpath -m "$BACKUP_ROOT")"
[[ -d "$DATA_DIR" ]] || die "数据目录不存在：$DATA_DIR"
case "$BACKUP_ROOT/" in "$DATA_DIR/"*) die "备份目录不能位于数据目录内部" ;; esac

destination="$BACKUP_ROOT/$LABEL"
[[ ! -e "$destination" ]] || die "备份已存在：$destination"
mkdir -p "$destination"
cp -a "$DATA_DIR" "$destination/data"

for relative in .env config/config.local.yaml; do
  if [[ -f "$PROJECT_ROOT/$relative" ]]; then
    mkdir -p "$destination/$(dirname -- "$relative")"
    cp -a "$PROJECT_ROOT/$relative" "$destination/$relative"
  fi
done

git -C "$PROJECT_ROOT" rev-parse HEAD > "$destination/source-commit.txt" 2>/dev/null \
  || printf 'unknown\n' > "$destination/source-commit.txt"
(
  cd "$destination"
  find . -type f ! -name SHA256SUMS -print0 \
    | sort -z | xargs -0 sha256sum > SHA256SUMS
)
printf '%s\n' "$destination"
