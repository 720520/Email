"""后台用户仓储。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppUser


class UserRepository:
    @staticmethod
    def find_by_username(session: Session, username: str) -> AppUser | None:
        return session.scalar(select(AppUser).where(AppUser.username == username))

    @staticmethod
    def get(session: Session, user_id: int) -> AppUser | None:
        return session.get(AppUser, user_id)
