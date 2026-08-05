"""在不回显密钥的情况下初始化本机 .env 业务安全密钥。"""

from __future__ import annotations

import argparse
import secrets
from pathlib import Path

from app.core.config import PROJECT_ROOT
from app.core.files import atomic_write_bytes

_KEY_NAMES = (
    "FUND_NAV_SECURITY__CREDENTIAL_ENCRYPTION_KEY",
    "FUND_NAV_SECURITY__AUDIT_SIGNING_KEY",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="安全初始化邮箱凭据和审计专用密钥")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=PROJECT_ROOT / ".env",
        help="目标 .env 路径，默认使用项目根目录 .env",
    )
    return parser.parse_args()


def initialize_security_keys(path: Path) -> tuple[str, ...]:
    """只补充缺失或空值，不覆盖已有密钥，也不向终端返回密钥内容。"""

    original = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = original.splitlines()
    positions: dict[str, int] = {}
    values: dict[str, str] = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name in _KEY_NAMES:
            positions[name] = index
            values[name] = value.strip()

    created: list[str] = []
    for name in _KEY_NAMES:
        if values.get(name):
            continue
        new_line = f"{name}={secrets.token_urlsafe(32)}"
        if name in positions:
            lines[positions[name]] = new_line
        else:
            lines.append(new_line)
        created.append(name)

    if created:
        content = "\n".join(lines).rstrip("\n") + "\n"
        atomic_write_bytes(path, content.encode("utf-8"))
    return tuple(created)


def main() -> int:
    args = _parse_args()
    created = initialize_security_keys(args.env_file.resolve())
    if created:
        print(f"已安全写入 {len(created)} 个独立业务密钥；密钥内容不会显示。")
        print("请重启后端使新密钥生效。")
    else:
        print("两个独立业务密钥均已存在，未修改 .env。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
