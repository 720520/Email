"""创建或更新本地后台管理员账号。"""

from __future__ import annotations

import argparse
import getpass

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.models import UserRole
from app.db.session import get_database_manager
from app.services.auth_service import AuthService
from app.services.foundation_service import FoundationService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="创建基金运营后台管理员")
    parser.add_argument("--username", default="admin", help="登录用户名，默认 admin")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    password = getpass.getpass("请输入密码（至少 10 个字符）: ")
    confirmation = getpass.getpass("请再次输入密码: ")
    if password != confirmation:
        print("两次输入的密码不一致")
        return 2

    settings = get_settings()
    configure_logging(settings)
    manager = get_database_manager()
    try:
        with manager.session_factory() as session, session.begin():
            foundation = FoundationService(settings).ensure(session)
            user = AuthService().create_user(
                session,
                username=args.username,
                password=password,
                role=UserRole.ADMIN,
                tenant_id=foundation.tenant_id,
                is_platform_admin=True,
            )
        print(f"管理员已创建: {user.username}")
        return 0
    except ValueError as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
