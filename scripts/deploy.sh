#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY_URL="${FUND_NAV_REPOSITORY_URL:-https://github.com/720520/Email.git}"
BRANCH="${FUND_NAV_DEPLOY_BRANCH:-main}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
INSTALL_DIR="${FUND_NAV_INSTALL_DIR:-$SOURCE_ROOT}"
BACKUP_ROOT="${FUND_NAV_BACKUP_DIR:-$INSTALL_DIR/backups}"
SKIP_TESTS=0

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
success() { printf '\033[1;32m%s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$1"; }
die() { printf '\n\033[1;31m部署失败：%s\033[0m\n' "$1" >&2; exit 1; }

usage() {
  cat <<EOF
用法：./一键部署.sh [选项]

从 GitHub 拉取 ${BRANCH} 分支，备份业务数据，安装依赖、迁移数据库并启动服务。

  --install-dir DIR  部署目录（默认当前项目目录）
  --branch NAME      部署分支（默认 main）
  --skip-tests       跳过后端测试和前端类型检查
  -h, --help         显示帮助

也可通过环境变量配置：
  FUND_NAV_REPOSITORY_URL、FUND_NAV_INSTALL_DIR、FUND_NAV_DEPLOY_BRANCH、
  FUND_NAV_BACKUP_DIR
EOF
}

while (($#)); do
  case "$1" in
    --install-dir)
      (($# >= 2)) || die "--install-dir 需要目录"
      INSTALL_DIR="$(realpath -m "$2")"
      BACKUP_ROOT="${FUND_NAV_BACKUP_DIR:-$INSTALL_DIR/backups}"
      shift
      ;;
    --branch)
      (($# >= 2)) || die "--branch 需要分支名"
      BRANCH="$2"
      shift
      ;;
    --skip-tests) SKIP_TESTS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "未知选项：$1（使用 --help 查看帮助）" ;;
  esac
  shift
done

for command_name in git curl sha256sum; do
  command -v "$command_name" >/dev/null 2>&1 || die "缺少命令：$command_name"
done

if [[ ! -d "$INSTALL_DIR/.git" ]]; then
  [[ ! -e "$INSTALL_DIR" ]] || [[ -z "$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]] \
    || die "部署目录不是 Git 仓库且不为空：$INSTALL_DIR"
  step "首次拉取项目"
  mkdir -p "$(dirname -- "$INSTALL_DIR")"
  git clone --branch "$BRANCH" --single-branch "$REPOSITORY_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"
[[ -x scripts/start.sh ]] || die "部署目录不是有效项目：$INSTALL_DIR"

if [[ -n "$(git status --short --untracked-files=no)" ]]; then
  die "部署目录存在未提交的代码修改，请先提交或还原后再部署"
fi

step "检查远程更新"
git fetch --prune origin "$BRANCH"
git merge-base --is-ancestor HEAD "origin/$BRANCH" \
  || die "本地代码与 origin/$BRANCH 已分叉，已停止以防覆盖代码"

old_commit="$(git rev-parse HEAD)"
new_commit="$(git rev-parse "origin/$BRANCH")"
printf '当前版本：%s\n目标版本：%s\n' "${old_commit:0:12}" "${new_commit:0:12}"

timestamp="$(date +%Y%m%d-%H%M%S)"
backup_dir="$BACKUP_ROOT/$timestamp"
mkdir -p "$backup_dir"

step "备份业务数据和本地配置"
for path in data .env config/config.local.yaml; do
  if [[ -e "$path" ]]; then
    mkdir -p "$backup_dir/$(dirname -- "$path")"
    cp -a "$path" "$backup_dir/$path"
  fi
done
printf '%s\n' "$old_commit" > "$backup_dir/source-commit.txt"
success "备份完成：$backup_dir"

if [[ "$old_commit" != "$new_commit" ]]; then
  step "快进更新代码"
  git merge --ff-only "origin/$BRANCH"
else
  success "代码已是最新版本。"
fi

step "停止旧服务"
./scripts/start.sh --stop || true

step "准备运行环境并迁移数据库"
./scripts/start.sh --setup-only

if ((!SKIP_TESTS)); then
  step "执行部署前检查"
  ./.venv/bin/python -m pytest backend/tests/unit -q
  (cd frontend && "$INSTALL_DIR/scripts/pnpm.sh" type-check)
fi

step "构建前端"
(cd frontend && "$INSTALL_DIR/scripts/pnpm.sh" build)

step "重启服务"
FUND_NAV_BACKEND_HOST=0.0.0.0 FUND_NAV_FRONTEND_HOST=0.0.0.0 \
  FUND_NAV_FRONTEND_MODE=preview \
  ./scripts/start.sh --no-browser

step "验证服务"
curl -fsS --max-time 5 http://127.0.0.1:8000/api/v1/health/live >/dev/null \
  || die "后端健康检查失败，请查看 logs/backend.log"
curl -fsS --max-time 5 http://127.0.0.1:5173 >/dev/null \
  || die "前端健康检查失败，请查看 logs/frontend.log"

lan_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
success "部署完成，版本：${new_commit:0:12}"
printf '本机访问：http://127.0.0.1:5173\n'
if [[ -n "$lan_ip" ]]; then
  printf '内网访问：http://%s:5173\n' "$lan_ip"
fi
printf '本次备份：%s\n' "$backup_dir"
