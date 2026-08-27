#!/usr/bin/env bash
set -Eeuo pipefail

export PYTHONIOENCODING=utf-8

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
VENV_DIR="$PROJECT_ROOT/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
TOOLS_DIR="$PROJECT_ROOT/.tools"
UV="$TOOLS_DIR/bin/uv"
PNPM="$SCRIPT_DIR/pnpm.sh"
LOG_DIR="$PROJECT_ROOT/logs"
RUN_DIR="$PROJECT_ROOT/.codex_tmp/run"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
REPORT_WORKER_PID_FILE="$RUN_DIR/report-worker.pid"
PARSE_WORKER_PID_FILE="$RUN_DIR/parse-worker.pid"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
REPORT_WORKER_LOG="$LOG_DIR/report-worker.log"
PARSE_WORKER_LOG="$LOG_DIR/parse-worker.log"
BACKEND_HOST="${FUND_NAV_BACKEND_HOST:-0.0.0.0}"
FRONTEND_HOST="${FUND_NAV_FRONTEND_HOST:-127.0.0.1}"
FRONTEND_MODE="${FUND_NAV_FRONTEND_MODE:-dev}"

SETUP_ONLY=0
NO_BROWSER=0
STOP_ONLY=0
ADMIN_USERNAME="admin"

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
success() { printf '\033[1;32m%s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$1"; }
die() { printf '\n\033[1;31m启动失败：%s\033[0m\n' "$1" >&2; exit 1; }

usage() {
  cat <<'EOF'
用法：./一键启动.sh [选项]

  --no-browser           启动后不自动打开浏览器
  --setup-only           只安装依赖、生成密钥和迁移数据库
  --admin-username NAME  首次创建的管理员用户名（默认 admin）
  --stop                 停止由本脚本启动的前后端服务
  -h, --help             显示帮助
EOF
}

while (($#)); do
  case "$1" in
    --no-browser) NO_BROWSER=1 ;;
    --setup-only) SETUP_ONLY=1 ;;
    --stop) STOP_ONLY=1 ;;
    --admin-username)
      (($# >= 2)) || die "--admin-username 需要用户名"
      ADMIN_USERNAME="$2"
      shift
      ;;
    -h|--help) usage; exit 0 ;;
    *) die "未知选项：$1（使用 --help 查看帮助）" ;;
  esac
  shift
done

mkdir -p "$LOG_DIR" "$RUN_DIR" "$TOOLS_DIR/bin"
cd "$PROJECT_ROOT"

pid_is_running() {
  local pid_file="$1" pid
  [[ -f "$pid_file" ]] || return 1
  read -r pid < "$pid_file" || return 1
  [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null
}

stop_service() {
  local name="$1" pid_file="$2" pid
  if ! pid_is_running "$pid_file"; then
    rm -f "$pid_file"
    warn "$name 未运行。"
    return
  fi
  read -r pid < "$pid_file"
  kill "$pid"
  for _ in {1..20}; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL "$pid"
  fi
  rm -f "$pid_file"
  success "$name 已停止。"
}

stop_onlyoffice() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker compose -f "$PROJECT_ROOT/compose.onlyoffice.yaml" stop onlyoffice-documentserver \
      >/dev/null 2>&1 || true
    success "OnlyOffice 已停止。"
  fi
}

if ((STOP_ONLY)); then
  step "停止基金运营系统"
  stop_service "前端" "$FRONTEND_PID_FILE"
  stop_service "附件解析 Worker" "$PARSE_WORKER_PID_FILE"
  stop_service "报表 Worker" "$REPORT_WORKER_PID_FILE"
  stop_service "后端" "$BACKEND_PID_FILE"
  stop_onlyoffice
  exit 0
fi

python_supported() {
  "$1" -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 13) else 1)' >/dev/null 2>&1
}

ensure_uv() {
  [[ -x "$UV" ]] && return
  command -v curl >/dev/null 2>&1 || die "缺少 curl，无法自动安装 Python 环境管理器 uv。"
  step "安装项目内置 uv"
  local installer
  installer="$(mktemp)"
  curl -LsSf https://astral.sh/uv/install.sh -o "$installer" || die "uv 安装器下载失败"
  UV_INSTALL_DIR="$TOOLS_DIR/bin" sh "$installer" || die "uv 安装失败"
  rm -f "$installer"
}

ensure_python_environment() {
  if [[ -x "$VENV_PYTHON" ]] && python_supported "$VENV_PYTHON"; then
    return
  fi

  step "创建 Python 3.12 虚拟环境"
  local candidate=""
  for executable in python3.12 python3.11 python3 python; do
    if command -v "$executable" >/dev/null 2>&1 && python_supported "$(command -v "$executable")"; then
      candidate="$(command -v "$executable")"
      break
    fi
  done

  if [[ -n "$candidate" ]] && "$candidate" -m venv "$VENV_DIR" >/dev/null 2>&1; then
    return
  fi

  ensure_uv
  UV_PYTHON_INSTALL_DIR="$TOOLS_DIR/python" UV_CACHE_DIR="$PROJECT_ROOT/.cache/uv" \
    "$UV" python install 3.12
  UV_PYTHON_INSTALL_DIR="$TOOLS_DIR/python" UV_CACHE_DIR="$PROJECT_ROOT/.cache/uv" \
    "$UV" venv --python 3.12 "$VENV_DIR"
}

ensure_backend_dependencies() {
  local project_file="$PROJECT_ROOT/backend/pyproject.toml"
  local marker="$VENV_DIR/.fund-nav-pyproject.sha256"
  local expected installed=""
  expected="$(sha256sum "$project_file" | awk '{print $1}')"
  [[ -f "$marker" ]] && read -r installed < "$marker"

  if "$VENV_PYTHON" -c \
    'import alembic, cryptography, fastapi, imapclient, openpyxl, pandas, sqlalchemy, uvicorn, xlrd' \
    >/dev/null 2>&1; then
    if [[ "$installed" == "$expected" ]]; then
      return
    fi
    # 兼容在引入 Linux 启动器之前已安装好的虚拟环境。
    if [[ -z "$installed" ]]; then
      printf '%s\n' "$expected" > "$marker"
      return
    fi
  fi

  step "安装后端依赖"
  ensure_uv
  UV_CACHE_DIR="$PROJECT_ROOT/.cache/uv" "$UV" pip install \
    --python "$VENV_PYTHON" -e "$PROJECT_ROOT/backend"
  printf '%s\n' "$expected" > "$marker"
}

ensure_node() {
  if ! command -v node >/dev/null 2>&1 && [[ -x /opt/codex-desktop/resources/node-runtime/bin/node ]]; then
    export PATH="/opt/codex-desktop/resources/node-runtime/bin:$PATH"
  fi
  command -v node >/dev/null 2>&1 || die "未找到 Node.js。请安装 Node.js 22/24 LTS 后重试。"
  local version major minor
  version="$(node --version | sed 's/^v//')"
  major="${version%%.*}"
  minor="${version#*.}"; minor="${minor%%.*}"
  if ((major < 22 || major >= 25)); then
    die "Node.js $version 不受支持，项目需要 Node.js 22 或 24 LTS。"
  fi
}

pnpm() {
  "$PNPM" "$@"
}

ensure_frontend_dependencies() {
  [[ -x "$PNPM" ]] || die "缺少 pnpm 启动器：$PNPM"
  local marker="$FRONTEND_DIR/node_modules/.fund-nav-lock.sha256"
  local expected installed=""
  expected="$(sha256sum "$FRONTEND_DIR/package.json" "$FRONTEND_DIR/pnpm-lock.yaml" | sha256sum | awk '{print $1}')"
  [[ -f "$marker" ]] && read -r installed < "$marker"
  if [[ -d "$FRONTEND_DIR/node_modules" ]]; then
    if [[ "$installed" == "$expected" ]]; then
      return
    fi
    # 首次切换到 Linux 启动器时接管已有的 node_modules。
    if [[ -z "$installed" && -x "$FRONTEND_DIR/node_modules/.bin/vite" ]]; then
      printf '%s\n' "$expected" > "$marker"
      return
    fi
  fi
  step "安装前端依赖"
  (cd "$FRONTEND_DIR" && pnpm install --frozen-lockfile)
  printf '%s\n' "$expected" > "$marker"
}

http_ready() {
  curl -fsS --max-time 2 "$1" >/dev/null 2>&1
}

port_in_use() {
  (echo >/dev/tcp/127.0.0.1/"$1") >/dev/null 2>&1
}

start_backend() {
  if http_ready "http://127.0.0.1:8000/api/v1/health/live"; then
    warn "后端已在运行。"
    return
  fi
  pid_is_running "$BACKEND_PID_FILE" && stop_service "旧后端进程" "$BACKEND_PID_FILE"
  port_in_use 8000 && die "8000 端口已被其他程序占用。"
  step "启动后端 http://127.0.0.1:8000"
  nohup "$VENV_PYTHON" -m uvicorn app.main:app --app-dir backend \
    --host "$BACKEND_HOST" --port 8000 >>"$BACKEND_LOG" 2>&1 &
  printf '%s\n' "$!" > "$BACKEND_PID_FILE"
}

start_frontend() {
  if http_ready "http://127.0.0.1:5173"; then
    warn "前端已在运行。"
    return
  fi
  pid_is_running "$FRONTEND_PID_FILE" && stop_service "旧前端进程" "$FRONTEND_PID_FILE"
  port_in_use 5173 && die "5173 端口已被其他程序占用。"
  step "启动前端 http://127.0.0.1:5173"
  local frontend_command="dev"
  if [[ "$FRONTEND_MODE" == "preview" ]]; then
    [[ -f "$FRONTEND_DIR/dist/index.html" ]] || die "缺少前端构建产物，请先执行 pnpm build。"
    frontend_command="preview"
  elif [[ "$FRONTEND_MODE" != "dev" ]]; then
    die "不支持的 FUND_NAV_FRONTEND_MODE：$FRONTEND_MODE"
  fi
  (cd "$FRONTEND_DIR" && nohup "$PNPM" \
    "$frontend_command" --host "$FRONTEND_HOST" --port 5173 \
    >>"$FRONTEND_LOG" 2>&1 & echo "$!" > "$FRONTEND_PID_FILE")
}

start_report_worker() {
  if pid_is_running "$REPORT_WORKER_PID_FILE"; then
    warn "报表 Worker 已在运行。"
    return
  fi
  step "启动批量报表 Worker"
  nohup "$VENV_PYTHON" -m app.cli.report_batch_worker \
    >>"$REPORT_WORKER_LOG" 2>&1 &
  printf '%s\n' "$!" > "$REPORT_WORKER_PID_FILE"
}

start_parse_worker() {
  if pid_is_running "$PARSE_WORKER_PID_FILE"; then
    warn "附件解析 Worker 已在运行。"
    return
  fi
  step "启动附件解析 Worker"
  nohup "$VENV_PYTHON" -m app.cli.attachment_parse_worker \
    >>"$PARSE_WORKER_LOG" 2>&1 &
  printf '%s\n' "$!" > "$PARSE_WORKER_PID_FILE"
}

start_onlyoffice() {
  if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    warn "未安装 Docker Compose，OnlyOffice 在线预览暂不可用，PPTX 下载不受影响。"
    return
  fi
  if ! docker info >/dev/null 2>&1; then
    warn "当前登录会话无权访问 Docker daemon。"
    warn "请注销 Linux 用户并重新登录，然后再执行一键启动。"
    warn "OnlyOffice 暂未启动，PPTX 下载不受影响。"
    return
  fi
  step "启动 OnlyOffice Document Server"
  docker compose -f "$PROJECT_ROOT/compose.onlyoffice.yaml" up -d onlyoffice-documentserver
}

printf '\033[1;32m基金运营邮件系统 - Linux 一键启动\033[0m\n'
printf '项目目录：%s\n' "$PROJECT_ROOT"

ensure_python_environment
ensure_backend_dependencies
ensure_node
ensure_frontend_dependencies

if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
  step "创建本地 .env"
  cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
fi

step "初始化业务安全密钥"
"$VENV_PYTHON" -m app.cli.init_security_keys

step "执行数据库迁移"
"$VENV_PYTHON" -m alembic -c backend/alembic.ini upgrade head

if ((SETUP_ONLY)); then
  success "环境准备完成。"
  exit 0
fi

admin_count="$("$VENV_PYTHON" -c 'from sqlalchemy import func, select; from app.db.models import AppUser; from app.db.session import get_database_manager; s=get_database_manager().session_factory(); print(s.scalar(select(func.count(AppUser.id)).where(AppUser.is_active.is_(True), AppUser.is_platform_admin.is_(True))) or 0); s.close()')"
if [[ "$admin_count" == "0" ]]; then
  step "创建首个平台管理员"
  warn "请输入至少 10 位密码，输入时不会显示。"
  "$VENV_PYTHON" -m app.cli.create_admin --username "$ADMIN_USERNAME"
fi

start_backend
start_report_worker
start_parse_worker
start_onlyoffice
start_frontend

step "等待系统就绪"
ready=0
for _ in {1..60}; do
  if http_ready "http://127.0.0.1:8000/api/v1/health/live" && http_ready "http://127.0.0.1:5173"; then
    ready=1
    break
  fi
  sleep 1
done

if ((ready)); then
  success "系统启动成功：http://127.0.0.1:5173"
  if ((!NO_BROWSER)) && command -v xdg-open >/dev/null 2>&1; then
    nohup xdg-open http://127.0.0.1:5173 >/dev/null 2>&1 &
  fi
else
  warn "服务已启动，但 60 秒内未就绪。"
  printf '后端日志：%s\n前端日志：%s\n' "$BACKEND_LOG" "$FRONTEND_LOG"
  exit 1
fi

printf '停止服务：%s --stop\n' "$PROJECT_ROOT/一键启动.sh"
