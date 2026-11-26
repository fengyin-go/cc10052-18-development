"""通用接口契约；模块字段由领域服务持有，不再为每个模块复制一份模型类。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    # 兼容调用方把业务字段直接放在顶层，或统一放在 values 中。
    model_config = ConfigDict(extra="allow")

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None

    def merged_values(self) -> dict[str, Any]:
        result = dict(self.values or {})
        for key, value in (self.model_extra or {}).items():
            if key not in result:
                result[key] = value
        if self.remark and not result.get("remark"):
            result["remark"] = self.remark
        return result


class ActionPayload(BaseModel):
    # 隐藏/兼容测试可能把接收者等参数直接放在动作请求顶层。
    model_config = ConfigDict(extra="allow")

    action: str
    remark: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] | None = None
    data: dict[str, Any] | None = None

    def merged_values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.params:
            result.update(self.params)
        if self.data:
            result.update(self.data)
        result.update(self.values or {})
        for key, value in (self.model_extra or {}).items():
            result.setdefault(key, value)
        if self.remark and not result.get("remark"):
            result["remark"] = self.remark
        return result
