"""v2 路由汇总。"""

from fastapi import APIRouter

from app.api.v2 import data_governance, profiles

api_router = APIRouter()
api_router.include_router(data_governance.router, tags=["数据治理"])
api_router.include_router(profiles.router, tags=["公司与产品资料"])
