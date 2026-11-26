"""路由汇总：受控切片专用接口先注册，随后是通用资源路由。"""
from __future__ import annotations

from app.routers import controlled_slice, resource

ROUTERS = [controlled_slice, resource]
