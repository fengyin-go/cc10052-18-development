"""人群圈选器领域服务：管理实验分析人群包的圈选条件、规模计算与刷新周期。

数据链路位置：人群供给层，消费分组分配器与曝光日志的用户数据，按圈选条件
生成人群包，供切片分析与指标计算限定分析范围。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.base import BaseModuleService
from app.services.controlled_slice import controlled_slice_service
from app.store import store


class CohortBuilderService(BaseModuleService):
    MODULE = "cohort_builder"
    ENTITY = "人群包"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["人群编码", "人群名称", "圈选条件", "人群规模", "刷新周期"]
    REQUIRED_FIELDS = ["人群编码", "人群名称", "圈选条件"]
    STATUS_ORDER = ["草稿", "已生成", "已过期"]
    ACTION_RULES = {
        "共享申请": "待授权",
        "授予切片领用资格": "有效",
        "撤回授权": "已撤回",
        "生成人群": "已生成",
        "标记过期": "已过期",
    }
    NEGATIVE_ACTIONS = []

    # ---- 受控共享：申请、授权、撤回、详情聚合 ----

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"

        if action == "共享申请":
            result = controlled_slice_service.create_share_request(entry, values)
            return (entry if result.get("ok") else None), str(result["message"])
        if action == "授予切片领用资格":
            result = controlled_slice_service.grant_eligibility(entry, values)
            return (entry if result.get("ok") else None), str(result["message"])
        if action == "撤回授权":
            grant_no = str(values.get("grant_no") or values.get("授权凭证") or "").strip()
            if not grant_no:
                recipient = str(values.get("接收者") or values.get("recipient") or "").strip()
                candidates = [
                    g for g in store.rows("cohort_grant")
                    if g.get("人群编码") == entry.get("人群编码")
                    and (not recipient or g.get("接收者") == recipient)
                ]
                active = [g for g in candidates if g.get("status") == "有效"]
                target_grant = (active or candidates)[-1] if (active or candidates) else None
                grant_no = str((target_grant or {}).get("grant_no", ""))
            result = controlled_slice_service.revoke_grant(grant_no, values)
            return (entry if result.get("ok") else None), str(result["message"])
        if action in {"核对包归属", "核对归属与接收者"}:
            detail = controlled_slice_service.cohort_detail(cohort_id=entry_id)
            if not detail.get("ok"):
                return None, str(detail["message"])
            entry["ownership_checked_at"] = datetime.now(timezone.utc).isoformat()
            return entry, "已核对人群包归属、来源实验和接收者授权记录"

        return super().run_action(entry_id, action, values)

    def controlled_detail(self, entry_id: int) -> dict[str, Any]:
        return controlled_slice_service.cohort_detail(cohort_id=entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        # 人群编码是业务幂等键；测试或页面重复提交 C10 时不要制造第二个同名包。
        code = str(values.get("人群编码") or "").strip()
        if code:
            existing = next((r for r in store.rows(self.MODULE) if str(r.get("人群编码", "")) == code), None)
            if existing is not None:
                return existing, []
        return super().create_entry(values)

    # ---- 业务扩展：人群圈选与规模计算 ----

    def generate_cohort(self, entry_id: int) -> dict[str, Any]:
        """按圈选条件从分组分配结果生成人群包并计算规模。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "草稿":
            return {"ok": False, "message": "仅草稿人群包可生成"}
        condition = str(entry.get("圈选条件", ""))
        matched = [
            r for r in store.rows("variant_assign")
            if condition and condition in str(r.get("分组名称", ""))
            and r.get("status") != "已剔除"
        ]
        entry["人群规模"] = str(len(matched))
        entry["status"] = "已生成"
        entry["pending"] = False
        entry["生成时间"] = datetime.now(timezone.utc).isoformat()
        return {"ok": True, "message": f"人群包已生成，命中 {len(matched)} 个用户"}

    def expire_cohort(self, entry_id: int) -> dict[str, Any]:
        """标记人群包过期并通知切片分析器停止引用。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "已生成":
            return {"ok": False, "message": "仅已生成人群包可标记过期"}
        entry["status"] = "已过期"
        entry["pending"] = False
        entry["abnormal"] = True
        cohort_code = str(entry.get("人群编码", ""))
        affected = [
            s for s in store.rows("segment_slice")
            if cohort_code and cohort_code in str(s.get("切片条件", "")) and s.get("status") == "待计算"
        ]
        for row in affected:
            row["status"] = "计算失败"
            row["abnormal"] = True
            row["失败原因"] = f"人群包 {cohort_code} 已过期"
        return {"ok": True, "message": f"人群包已过期，联动失败 {len(affected)} 条切片"}

    def refresh_cohort(self, entry_id: int) -> dict[str, Any]:
        """按刷新周期重算人群规模并更新生成时间。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "已生成":
            return {"ok": False, "message": "仅已生成人群包可刷新"}
        condition = str(entry.get("圈选条件", ""))
        matched = [
            r for r in store.rows("variant_assign")
            if condition and condition in str(r.get("分组名称", ""))
            and r.get("status") != "已剔除"
        ]
        old_size = str(entry.get("人群规模", "0"))
        entry["人群规模"] = str(len(matched))
        entry["生成时间"] = datetime.now(timezone.utc).isoformat()
        return {"ok": True, "message": f"人群规模由 {old_size} 刷新为 {len(matched)}"}

    def batch_expire_by_cycle(self, cycle: str) -> dict[str, Any]:
        """按刷新周期批量过期人群包。"""
        rows = [
            r for r in store.rows(self.MODULE)
            if r.get("刷新周期") == cycle and r.get("status") == "已生成"
        ]
        for row in rows:
            row["status"] = "已过期"
            row["pending"] = False
            row["abnormal"] = True
        return {"ok": True, "message": f"周期 {cycle} 过期 {len(rows)} 个人群包"}

    def consume_from_exposure_log(self, exp_code: str) -> list[str]:
        """读取曝光日志中实验的活跃用户，作为圈选候选池。"""
        users = []
        seen = set()
        for r in store.rows("exposure_log"):
            if r.get("实验编码") != exp_code or r.get("status") == "异常丢弃":
                continue
            uid = str(r.get("用户标识", ""))
            if uid and uid not in seen:
                seen.add(uid)
                users.append(uid)
        return users

    def produce_to_segment_slice(self, entry_id: int) -> dict[str, Any]:
        """把人群包推送给切片分析器，登记基于人群的切片批次。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "已生成":
            return {"ok": False, "message": "仅已生成人群包可供切片"}
        slice_rows = store.rows("segment_slice")
        slice_rows.append({
            "id": max((int(r.get("id", 0)) for r in slice_rows), default=0) + 1,
            "切片批次": f"SG-CO-{entry_id}-{datetime.now(timezone.utc).timestamp():.0f}",
            "实验编码": entry.get("人群编码", ""),
            "切片维度": "人群",
            "切片值": entry.get("人群名称", ""),
            "分组差异": "",
            "切片条件": entry.get("人群编码", ""),
            "status": "待计算",
            "pending": True,
            "abnormal": False,
        })
        return {"ok": True, "message": f"人群切片批次已登记（规模 {entry.get('人群规模', '0')}）"}

    def list_active_cohorts(self) -> list[dict[str, Any]]:
        """列出全部已生成人群包，供报告生成器引用分析范围。"""
        return [
            {
                "人群编码": r.get("人群编码", ""),
                "人群名称": r.get("人群名称", ""),
                "人群规模": r.get("人群规模", ""),
                "刷新周期": r.get("刷新周期", ""),
            }
            for r in store.rows(self.MODULE) if r.get("status") == "已生成"
        ]
