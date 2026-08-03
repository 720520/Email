"""v1 路由汇总。"""

from fastapi import APIRouter

from app.api.v1 import auth, dashboard, emails, exceptions, fund_nav, health, operations

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["系统健康"])
api_router.include_router(auth.router, prefix="/auth", tags=["登录认证"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["运营概览"])
api_router.include_router(emails.router, prefix="/emails", tags=["邮件管理"])
api_router.include_router(fund_nav.router, prefix="/fund-nav", tags=["基金净值"])
api_router.include_router(exceptions.router, prefix="/exceptions", tags=["异常管理"])
api_router.include_router(operations.router, prefix="/operations", tags=["运营操作"])
