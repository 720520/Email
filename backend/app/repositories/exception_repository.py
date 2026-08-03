"""运营异常仓储。"""

from sqlalchemy.orm import Session

from app.db.models import ExceptionRecord


class ExceptionRepository:
    @staticmethod
    def add(session: Session, exception: ExceptionRecord) -> ExceptionRecord:
        session.add(exception)
        return exception
