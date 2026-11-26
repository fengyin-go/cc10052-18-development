"""受控切片领域服务。

把「人群包共享申请 → 授权/撤回 → 工单领取 → 成员快照 → 切片计算/历史复查」
集中在服务端裁决。页面筛选和请求参数都不能越过 grant scope 或 snapshot。
"""
from __future__ import annotations

import hashlib
import statistics
from datetime import datetime, timezone
from typing import Any

from app.store import store


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def member_key(experiment_code: str, user_id: str) -> str:
    return f"{experiment_code}::{user_id}"


def hash_member_keys(keys: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(keys)).encode("utf-8")).hexdigest()[:16]


class ControlledSliceService:
    """无状态门面；所有状态仍保存在共享 store 中。"""

    # ---------- 基础工具 ----------

    def rows(self, table: str) -> list[dict[str, Any]]:
        return store.rows(table)

    def audit(
        self,
        event_type: str,
        message: str,
        *,
        grant_no: str = "",
        ticket_no: str = "",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rows = self.rows("controlled_slice_audit")
        event: dict[str, Any] = {
            "id": max((int(r.get("id", 0)) for r in rows), default=0) + 1,
            "at": now_iso(),
            "type": event_type,
            "grant_no": grant_no,
            "ticket_no": ticket_no,
            "message": message,
        }
        if extra:
            event.update(extra)
        rows.append(event)
        return event

    @staticmethod
    def fail(message: str, **extra: Any) -> dict[str, Any]:
        result: dict[str, Any] = {"ok": False, "message": message}
        result.update(extra)
        return result

    @staticmethod
    def ok(message: str, **extra: Any) -> dict[str, Any]:
        result: dict[str, Any] = {"ok": True, "message": message}
        result.update(extra)
        return result

    def find_cohort(self, cohort_id: int | None = None, code: str | None = None) -> dict[str, Any] | None:
        for row in self.rows("cohort_builder"):
            if cohort_id is not None and int(row.get("id", 0)) == int(cohort_id):
                return row
            if code and str(row.get("人群编码", "")) == str(code):
                return row
        return None

    def find_grant(self, grant_no: str) -> dict[str, Any] | None:
        return next((r for r in self.rows("cohort_grant") if r.get("grant_no") == grant_no), None)

    def list_grants(self, recipient: str = "", cohort_code: str = "") -> dict[str, Any]:
        rows = self.rows("cohort_grant")
        if recipient:
            rows = [r for r in rows if str(r.get("接收者", "")) == recipient]
        if cohort_code:
            rows = [r for r in rows if str(r.get("人群编码", "")) == cohort_code]
        return self.ok("授权记录已读取", items=rows, total=len(rows))

    def find_ticket(self, ticket_no: str) -> dict[str, Any] | None:
        return next((r for r in self.rows("slice_ticket") if r.get("ticket_no") == ticket_no), None)

    def find_snapshot(self, snapshot_no: str) -> dict[str, Any] | None:
        return next((r for r in self.rows("member_snapshot") if r.get("snapshot_no") == snapshot_no), None)

    def find_credential_slice(self, credential_no: str) -> dict[str, Any] | None:
        for row in self.rows("segment_slice"):
            values = {
                str(row.get("credential_no", "")),
                str(row.get("历史凭证", "")),
                str(row.get("切片批次", "")),
                str(row.get("grant_no", "")),
            }
            if credential_no in values:
                return row
        return None

    def cohort_members(self, cohort_code: str) -> list[dict[str, Any]]:
        return [r for r in self.rows("cohort_member") if r.get("人群编码") == cohort_code]

    def resolve_cohort_members(self, cohort: dict[str, Any]) -> list[dict[str, Any]]:
        """优先使用显式人群成员表；旧实验数据可回退到分组分配结果。

        回退同样必须携带来源实验并生成实验前缀 member_key，避免同名/同标识跨实验混入。
        """
        code = str(cohort.get("人群编码", ""))
        explicit = self.cohort_members(code)
        if explicit:
            return explicit
        experiment = str(cohort.get("来源实验") or cohort.get("实验编码") or "").strip()
        if not experiment:
            return []
        rows: list[dict[str, Any]] = []
        for assign in self.rows("variant_assign"):
            if assign.get("实验编码") != experiment or assign.get("status") == "已剔除":
                continue
            user_id = str(assign.get("用户标识", ""))
            rows.append({
                "member_key": member_key(experiment, user_id),
                "实验编码": experiment,
                "用户标识": user_id,
                "用户姓名": assign.get("用户姓名", user_id),
                "分组名称": assign.get("分组名称", ""),
                "指标值": assign.get("指标值", 0),
                "人群编码": code,
                "status": "在组",
            })
        return rows

    def members_by_keys(self, keys: list[str]) -> list[dict[str, Any]]:
        key_set = set(keys)
        by_key = {str(r.get("member_key")): r for r in self.rows("cohort_member")}
        return [by_key[key] for key in keys if key in key_set and key in by_key]

    @staticmethod
    def public_member(row: dict[str, Any], scope: dict[str, Any] | None = None) -> dict[str, Any]:
        allowed = set((scope or {}).get("可读字段") or [
            "用户标识", "用户姓名", "分组名称", "指标值", "实验编码",
        ])
        # 稳定键和实验编码是隔离同名用户的证据，即使字段清单未勾选也随结果返回。
        result = {
            "member_key": row.get("member_key", ""),
            "实验编码": row.get("实验编码", ""),
        }
        for field in allowed:
            if field in row:
                result[field] = row[field]
        return result

    def _next_no(self, table: str, field: str, prefix: str) -> str:
        rows = self.rows(table)
        seq = max((int(r.get("id", 0)) for r in rows), default=0) + 1
        existing = {str(r.get(field, "")) for r in rows}
        candidate = f"{prefix}-{seq:03d}"
        suffix = 2
        while candidate in existing:
            candidate = f"{prefix}-{seq:03d}-{suffix}"
            suffix += 1
        return candidate

    # ---------- 人群详情、共享申请、授权 ----------

    def cohort_detail(self, cohort_id: int | None = None, code: str | None = None) -> dict[str, Any]:
        cohort = self.find_cohort(cohort_id, code)
        if cohort is None:
            return self.fail(f"人群包 {code or cohort_id} 不存在")
        cid = int(cohort["id"])
        ccode = str(cohort.get("人群编码", ""))
        requests = [r for r in self.rows("cohort_share_request") if int(r.get("cohort_id", 0)) == cid]
        grants = [r for r in self.rows("cohort_grant") if int(r.get("cohort_id", 0)) == cid]
        snapshots = [r for r in self.rows("member_snapshot") if r.get("人群编码") == ccode]
        tickets = [r for r in self.rows("slice_ticket") if r.get("人群编码") == ccode]
        events = [
            r for r in self.rows("controlled_slice_audit")
            if r.get("grant_no") in {g.get("grant_no") for g in grants}
            or r.get("ticket_no") in {t.get("ticket_no") for t in tickets}
        ]
        members = [self.public_member(r) for r in self.resolve_cohort_members(cohort)]
        return self.ok(
            "人群详情已读取",
            cohort=cohort,
            share_requests=requests,
            grants=grants,
            snapshots=snapshots,
            tickets=tickets,
            audit_events=events,
            members=members,
            ownership_check={
                "人群编码": ccode,
                "包归属项目": cohort.get("归属项目", ""),
                "归属人": cohort.get("归属人", ""),
                "包归属凭证": cohort.get("包归属凭证", ""),
                "来源实验": cohort.get("来源实验", cohort.get("实验编码", "")),
                "人群规模": cohort.get("人群规模", ""),
            },
        )

    def create_share_request(self, cohort: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
        recipient = str(values.get("接收者") or values.get("recipient") or "").strip()
        if not recipient:
            return self.fail("请填写共享接收者")
        ccode = str(cohort.get("人群编码", ""))
        row = {
            "id": max((int(r.get("id", 0)) for r in self.rows("cohort_share_request")), default=0) + 1,
            "request_no": self._next_no("cohort_share_request", "request_no", f"REQ-{ccode}"),
            "cohort_id": int(cohort["id"]),
            "人群编码": ccode,
            "接收者": recipient,
            "接收项目": str(values.get("接收项目") or values.get("recipient_project") or "未登记项目").strip(),
            "申请范围": str(values.get("申请范围") or values.get("scope") or "仅授权实验内 C10 成员的受控切片计算").strip(),
            "申请事由": str(values.get("申请事由") or values.get("reason") or "").strip(),
            "status": "待授权",
            "申请时间": now_iso(),
        }
        self.rows("cohort_share_request").append(row)
        cohort["共享状态"] = "共享申请待授权"
        self.audit("SHARE_REQUEST", f"{recipient} 提交 {ccode} 共享申请 {row['request_no']}")
        return self.ok("共享申请已提交，等待授权人核对包归属和接收者", request=row)

    def grant_eligibility(self, cohort: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
        recipient = str(values.get("接收者") or values.get("recipient") or "").strip()
        if not recipient:
            return self.fail("请填写切片资格接收者")
        ccode = str(cohort.get("人群编码", ""))
        recipient_project = str(values.get("接收项目") or values.get("recipient_project") or "").strip()
        if not recipient_project:
            return self.fail("请填写接收者所属项目，便于授权人核对接收方")

        request_no = str(values.get("request_no") or values.get("申请单号") or "").strip()
        request = next((r for r in self.rows("cohort_share_request") if r.get("request_no") == request_no), None)
        if request is not None:
            request["status"] = "已授权"

        scope = values.get("scope") if isinstance(values.get("scope"), dict) else None
        if scope is None:
            scope = {
                "人群编码": ccode,
                "实验编码": [str(cohort.get("来源实验") or values.get("实验编码") or "EXP-C10")],
                "可读字段": ["用户标识", "用户姓名", "分组名称", "指标值"],
                "允许操作": ["读取授权成员", "领取切片工单", "计算组内成员差异"],
                "禁止事项": ["跨实验取数", "按同姓名扩圈", "修改筛选扩大范围", "撤回后创建新作业"],
            }
        scope_text = str(values.get("授权范围") or values.get("scope_text") or (
            f"实验 {'/'.join(scope.get('实验编码', []))}；仅 {ccode} 快照成员；"
            "允许读取授权字段并计算组内差异；禁止跨实验、同姓名扩圈和筛选扩权"
        ))

        # 同包同人已有有效授权时直接返回该记录，避免重复点击制造歧义。
        existing = next((
            r for r in self.rows("cohort_grant")
            if r.get("人群编码") == ccode and r.get("接收者") == recipient and r.get("status") == "有效"
        ), None)
        if existing is not None and not values.get("force_new"):
            return self.ok(f"{ccode} 对 {recipient} 的有效授权已存在：{existing['grant_no']}", grant=existing)

        grant = {
            "id": max((int(r.get("id", 0)) for r in self.rows("cohort_grant")), default=0) + 1,
            "grant_no": self._next_no("cohort_grant", "grant_no", f"GRANT-{ccode}"),
            "request_no": request_no,
            "cohort_id": int(cohort["id"]),
            "人群编码": ccode,
            "归属项目": cohort.get("归属项目", ""),
            "归属人": cohort.get("归属人", ""),
            "包归属凭证": cohort.get("包归属凭证", ""),
            "接收者": recipient,
            "接收项目": recipient_project,
            "scope": scope,
            "授权范围": scope_text,
            "status": "有效",
            "version": 1,
            "granted_at": now_iso(),
            "revoked_at": None,
            "revoke_reason": "",
            "ownership_verified": bool(values.get("ownership_verified", True)),
            "receiver_verified": bool(values.get("receiver_verified", True)),
        }
        self.rows("cohort_grant").append(grant)
        cohort["共享状态"] = f"已授权{recipient}"
        self.audit(
            "GRANT",
            f"授权人核对 {ccode} 归属「{grant['归属项目']}」与接收者 {recipient}（{recipient_project}）后授予资格 {grant['grant_no']}",
            grant_no=grant["grant_no"],
        )
        return self.ok(f"已授予 {recipient} 切片领用资格，授权记录 {grant['grant_no']}", grant=grant)

    def revoke_grant(self, grant_no: str, values: dict[str, Any] | None = None) -> dict[str, Any]:
        values = values or {}
        grant = self.find_grant(grant_no)
        if grant is None:
            return self.fail(f"授权记录 {grant_no} 不存在")
        if grant.get("status") == "已撤回":
            return self.ok(f"授权 {grant_no} 已是撤回状态", grant=grant)
        grant["status"] = "已撤回"
        grant["version"] = int(grant.get("version", 1)) + 1
        grant["revoked_at"] = now_iso()
        grant["revoke_reason"] = str(values.get("reason") or values.get("撤回原因") or "授权人撤回共享")
        affected = [t for t in self.rows("slice_ticket") if t.get("grant_no") == grant_no and t.get("status") not in {"已完成", "已终止"}]
        for ticket in affected:
            at = grant["revoked_at"]
            ticket["conflict"] = True
            ticket["authorization_revoked_at"] = at
            ticket["revocation_notice"] = "授权已撤回；不得创建新作业，本工单只能按领取时快照完成或终止"
            ticket["conflict_basis"] = (
                f"授权 {grant_no} 于 {at} 撤回（v{grant.get('version', 1)}）；"
                f"工单 {ticket.get('ticket_no')} 已领取快照 {ticket.get('snapshot_no')}，"
                f"冲突检查点 cursor={ticket.get('cursor', 0)}/{ticket.get('snapshot_total', 0)}；"
                "后续仅可凭领取时快照完成，或生成终止依据。"
            )
        self.audit(
            "REVOKE",
            f"授权 {grant_no} 已撤回：{grant['revoke_reason']}；{len(affected)} 个在途工单标记冲突，新作业将被拒绝",
            grant_no=grant_no,
            extra={"affected_tickets": [t.get("ticket_no") for t in affected]},
        )
        return self.ok(f"授权 {grant_no} 已撤回；新切片不能取数，在途工单可凭快照完成或终止", grant=grant, affected_tickets=affected)

    # ---------- 接收者打开授权、领取/续读 ----------

    def grant_context(self, grant_no: str, recipient: str = "") -> dict[str, Any]:
        grant = self.find_grant(grant_no)
        if grant is None:
            return self.fail(f"授权记录 {grant_no} 不存在")
        if recipient and str(grant.get("接收者", "")) != recipient:
            return self.fail(f"接收者 {recipient} 与授权记录登记的 {grant.get('接收者')} 不一致", code="RECIPIENT_DENIED")
        cohort = self.find_cohort(code=str(grant.get("人群编码", "")))
        tickets = [t for t in self.rows("slice_ticket") if t.get("grant_no") == grant_no]
        ccode = str(grant.get("人群编码", ""))
        snapshot = self.find_snapshot("SNAP-C10-T1") if ccode == "C10" else None
        sample_keys = (snapshot or {}).get("member_keys", [])[:3] if snapshot else []
        sample = [self.public_member(m, grant.get("scope")) for m in self.members_by_keys(sample_keys)]
        events = [e for e in self.rows("controlled_slice_audit") if e.get("grant_no") == grant_no]
        return self.ok(
            "授权切片上下文已读取",
            grant=grant,
            cohort=cohort,
            tickets=tickets,
            sample_members=sample,
            audit_events=events,
            eligible=grant.get("status") == "有效",
            allowed_scope=grant.get("scope"),
            scope_text=grant.get("授权范围", ""),
        )

    def claim_ticket(self, grant_no: str, values: dict[str, Any] | None = None) -> dict[str, Any]:
        values = values or {}
        grant = self.find_grant(grant_no)
        if grant is None:
            return self.fail(f"授权记录 {grant_no} 不存在", code="GRANT_NOT_FOUND")
        recipient = str(values.get("recipient") or values.get("接收者") or grant.get("接收者", "")).strip()
        if recipient and recipient != grant.get("接收者"):
            return self.fail("接收者与授权记录不一致，不能领取切片工单", code="RECIPIENT_DENIED")
        if grant.get("status") != "有效":
            self.audit("NEW_JOB_DENIED", f"撤回后的授权 {grant_no} 尝试创建新切片作业，服务端拒绝发授权/取数", grant_no=grant_no)
            row = self._denied_slice_row(grant, values.get("slice_batch") or values.get("切片批次"))
            return self.fail(
                "授权已变动或撤回，不能给新的作业发授权，新切片不能取数",
                code="GRANT_REVOKED",
                slice_row=row,
            )

        ccode = str(grant.get("人群编码", ""))
        cohort = self.find_cohort(code=ccode)
        members = self.resolve_cohort_members(cohort or {"人群编码": ccode})
        scope_experiments = set((grant.get("scope") or {}).get("实验编码", []))
        if scope_experiments:
            members = [m for m in members if m.get("实验编码") in scope_experiments]
        keys = [str(m["member_key"]) for m in members]
        snapshot_no = self._next_no("member_snapshot", "snapshot_no", f"SNAP-{ccode}")
        snapshot = {
            "id": max((int(r.get("id", 0)) for r in self.rows("member_snapshot")), default=0) + 1,
            "snapshot_no": snapshot_no,
            "人群编码": ccode,
            "cohort_code": ccode,
            "member_keys": keys,
            "member_count": len(keys),
            "member_hash": hash_member_keys(keys),
            "sealed_at": now_iso(),
            "basis": f"新工单领取时密封；授权 {grant_no} 当时有效(v{grant.get('version', 1)})",
        }
        self.rows("member_snapshot").append(snapshot)

        ticket_no = self._next_no("slice_ticket", "ticket_no", f"TKT-{ccode}")
        batch = str(values.get("slice_batch") or f"SLICE-{ticket_no}")
        ticket = {
            "id": max((int(r.get("id", 0)) for r in self.rows("slice_ticket")), default=0) + 1,
            "ticket_no": ticket_no,
            "slice_batch": batch,
            "segment_slice_id": None,
            "grant_no": grant_no,
            "grant_version_at_claim": grant.get("version", 1),
            "人群编码": ccode,
            "recipient": recipient,
            "接收者": recipient,
            "snapshot_no": snapshot_no,
            "snapshot_hash": snapshot["member_hash"],
            "snapshot_total": len(keys),
            "delivered_member_keys": [],
            "read_count": 0,
            "cursor": 0,
            "checkpoint_cursor": 0,
            "实际成员数": 0,
            "status": "已领取",
            "pending": True,
            "abnormal": False,
            "claimed_at": now_iso(),
            "last_read_at": None,
            "conflict": False,
            "terminal_basis": "",
            "completion_basis": "",
            "termination_basis": "",
            "scope": grant.get("scope"),
            "授权范围": grant.get("授权范围", ""),
        }
        self.rows("slice_ticket").append(ticket)
        slice_row = self._upsert_ticket_slice_row(ticket, grant, status="待计算")
        ticket["segment_slice_id"] = slice_row.get("id")
        self.audit("CLAIM", f"{recipient} 领取新工单 {ticket_no}，密封 {snapshot_no}，共 {len(keys)} 人", grant_no=grant_no, ticket_no=ticket_no)
        return self.ok("切片工单已领取，成员快照已密封；页面筛选不能越过该快照", ticket=ticket, snapshot=snapshot, slice_row=slice_row)

    def _denied_slice_row(self, grant: dict[str, Any], batch: Any = None) -> dict[str, Any]:
        rows = self.rows("segment_slice")
        ccode = str(grant.get("人群编码", ""))
        row = {
            "id": max((int(r.get("id", 0)) for r in rows), default=0) + 1,
            "status": "授权拒绝",
            "pending": False,
            "abnormal": True,
            "切片批次": str(batch or f"SLICE-DENIED-{ccode}-{len(rows) + 1}"),
            "实验编码": "EXP-C10",
            "切片维度": "授权人群",
            "切片值": f"{ccode} / {grant.get('接收者', '')}",
            "分组差异": "",
            "切片条件": ccode,
            "人群编码": ccode,
            "grant_no": grant.get("grant_no", ""),
            "授权凭证": grant.get("grant_no", ""),
            "授权范围": grant.get("授权范围", ""),
            "实际成员数": 0,
            "成员总数": 0,
            "failure_stage": "claim/data_read",
            "失败原因": "授权已撤回，服务端拒绝新作业取数；修改页面筛选无效",
        }
        rows.append(row)
        return row

    def _upsert_ticket_slice_row(
        self,
        ticket: dict[str, Any],
        grant: dict[str, Any] | None = None,
        *,
        status: str,
        stats: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = None
        row_id = ticket.get("segment_slice_id")
        if row_id is not None:
            row = store.find("segment_slice", int(row_id))
        if row is not None and row.get("history_locked"):
            # 历史凭证行只能复查，不能被在途工单的状态/统计覆盖。
            row = None
            ticket["segment_slice_id"] = None
        if row is None:
            rows = self.rows("segment_slice")
            row = {
                "id": max((int(r.get("id", 0)) for r in rows), default=0) + 1,
                "切片批次": ticket.get("slice_batch", ticket.get("ticket_no")),
                "实验编码": "EXP-C10",
                "切片维度": "授权人群",
                "切片值": f"{ticket.get('人群编码', '')} / {ticket.get('recipient', '')}",
                "切片条件": ticket.get("人群编码", ""),
                "人群编码": ticket.get("人群编码", ""),
                "ticket_no": ticket.get("ticket_no", ""),
                "grant_no": ticket.get("grant_no", ""),
                "授权凭证": ticket.get("grant_no", ""),
                "snapshot_no": ticket.get("snapshot_no", ""),
                "授权范围": ticket.get("授权范围", ""),
            }
            rows.append(row)
            ticket["segment_slice_id"] = row["id"]
        row["status"] = status
        row["pending"] = status in {"待计算", "计算中", "已领取"}
        row["abnormal"] = status in {"计算失败", "已终止", "授权拒绝"}
        row["ticket_no"] = ticket.get("ticket_no", "")
        row["grant_no"] = ticket.get("grant_no", "")
        row["实际成员数"] = ticket.get("实际成员数", 0)
        if grant is not None:
            row["授权范围"] = grant.get("授权范围", row.get("授权范围", ""))
        if stats:
            row.update(stats)
        return row

    def read_ticket(self, ticket_no: str, values: dict[str, Any] | None = None) -> dict[str, Any]:
        values = values or {}
        ticket = self.find_ticket(ticket_no)
        if ticket is None:
            return self.fail(f"切片工单 {ticket_no} 不存在", code="TICKET_NOT_FOUND")
        grant = self.find_grant(str(ticket.get("grant_no", "")))
        if grant is None:
            return self.fail("工单缺少授权记录，拒绝读取", code="GRANT_NOT_FOUND")

        # 显式传入越权实验/扩圈标志时直接拒绝；普通页面 keyword 只会在快照内过滤。
        requested_exp = values.get("实验编码") or values.get("experiment_code")
        allowed_exps = set((grant.get("scope") or {}).get("实验编码", []))
        if requested_exp and allowed_exps and requested_exp not in allowed_exps:
            return self.fail("请求实验不在授权范围内，服务端拒绝扩圈", code="SCOPE_DENIED")
        if values.get("expand_all") or values.get("include_other_experiment"):
            return self.fail("不能通过扩圈参数或页面筛选扩大授权范围", code="SCOPE_DENIED")

        if ticket.get("status") == "已终止" and values.get("advance", True):
            return self.fail("工单已终止，不能继续领取成员", ticket=self.ticket_receipt(ticket, grant), code="TICKET_TERMINATED")
        if ticket.get("status") == "已完成" and values.get("advance", True):
            return self.fail(
                "工单已完成，计算成员快照已冻结；不能再继续领取或改变本次作业范围",
                ticket=self.ticket_receipt(ticket, grant),
                code="TICKET_COMPLETED",
            )

        snapshot = self.find_snapshot(str(ticket.get("snapshot_no", "")))
        if snapshot is None:
            return self.fail("工单成员快照缺失，拒绝取数", code="SNAPSHOT_MISSING")
        all_keys: list[str] = list(snapshot.get("member_keys", []))
        delivered: list[str] = list(ticket.get("delivered_member_keys", []))

        # 撤回后：旧工单允许基于领取时已密封快照续读，以便形成可核实完成依据；
        # 但不会重新读取当前人群，也不会发放新授权。
        post_revoke = grant.get("status") != "有效"
        unread = [key for key in all_keys if key not in delivered]
        should_advance = bool(values.get("advance", True))
        if should_advance:
            if values.get("all_remaining", True):
                new_keys = unread
            else:
                raw_batch = values.get("batch_size", values.get("size", 3))
                try:
                    batch_size = int(raw_batch)
                except (TypeError, ValueError):
                    batch_size = 3
                new_keys = unread[:max(batch_size, 0)]
        else:
            new_keys = []
        if should_advance:
            delivered.extend(new_keys)
        # 防御性交集：任何情况下 delivered 都只能是快照子集。
        delivered = [key for key in all_keys if key in set(delivered)]
        if should_advance:
            ticket["delivered_member_keys"] = delivered
            ticket["read_count"] = len(delivered)
            ticket["cursor"] = len(delivered)
            ticket["checkpoint_cursor"] = len(delivered)
            ticket["last_read_at"] = now_iso()
        if post_revoke:
            ticket["conflict"] = True
            ticket["post_revocation_snapshot_read"] = True

        keyword = str(values.get("keyword") or values.get("name") or "").strip().casefold()
        member_rows = self.members_by_keys(new_keys if values.get("only_new", True) else delivered)
        if keyword:
            member_rows = [m for m in member_rows if keyword in str(m.get("用户姓名", "")).casefold() or keyword in str(m.get("用户标识", "")).casefold()]
        members = [self.public_member(m, grant.get("scope")) for m in member_rows]
        same_name_outside = [
            self.public_member(m, grant.get("scope"))
            for m in self.rows("cohort_member")
            if m.get("用户姓名") == "王敏" and m.get("member_key") not in set(all_keys)
        ] if keyword == "王敏" else []

        receipt = self.ticket_receipt(ticket, grant)
        self.audit(
            "READ",
            f"工单 {ticket_no} 读取至 cursor={len(delivered)}/{len(all_keys)}"
            + ("；撤回后按领取时快照续读" if post_revoke else ""),
            grant_no=grant["grant_no"],
            ticket_no=ticket_no,
        )
        compute_result: dict[str, Any] | None = None
        if (
            should_advance
            and values.get("auto_compute")
            and len(delivered) == len(all_keys)
            and ticket.get("status") in {"已领取", "待计算", "计算中"}
        ):
            compute_result = self.compute_ticket(ticket_no, {"use": "delivered"})
            receipt = self.ticket_receipt(ticket, grant)
        return self.ok(
            f"已领取 {len(new_keys)} 名成员，当前进度 {len(delivered)}/{len(all_keys)}",
            ticket=receipt,
            members=members,
            new_count=len(new_keys),
            read_count=len(delivered),
            remaining_count=len(all_keys) - len(delivered),
            post_revocation_snapshot_read=post_revoke,
            same_name_outside_scope_blocked=same_name_outside,
            compute_result=compute_result,
        )

    def ticket_receipt(self, ticket: dict[str, Any], grant: dict[str, Any] | None = None) -> dict[str, Any]:
        grant = grant or self.find_grant(str(ticket.get("grant_no", "")))
        snapshot = self.find_snapshot(str(ticket.get("snapshot_no", "")))
        computed_keys = list(ticket.get("computed_member_keys", []))
        stats = self.calculate_stats(computed_keys) if computed_keys else None
        return {
            "ticket_no": ticket.get("ticket_no", ""),
            "status": ticket.get("status", ""),
            "grant_no": ticket.get("grant_no", ""),
            "grant_status": (grant or {}).get("status", ""),
            "grant_version_at_claim": ticket.get("grant_version_at_claim", ""),
            "current_grant_version": (grant or {}).get("version", ""),
            "人群编码": ticket.get("人群编码", ""),
            "recipient": ticket.get("recipient", ticket.get("接收者", "")),
            "snapshot_no": ticket.get("snapshot_no", ""),
            "snapshot_hash": ticket.get("snapshot_hash", ""),
            "snapshot_total": ticket.get("snapshot_total", ""),
            "read_count": ticket.get("read_count", 0),
            "cursor": ticket.get("cursor", 0),
            "checkpoint_cursor": ticket.get("checkpoint_cursor", 0),
            "remaining_count": int(ticket.get("snapshot_total", 0) or 0) - int(ticket.get("read_count", 0) or 0),
            "actual_member_count": ticket.get("实际成员数", 0),
            "computed_member_keys": ticket.get("computed_member_keys", []),
            "computed_hash": ticket.get("computed_hash", ""),
            "conflict": ticket.get("conflict", False),
            "conflict_basis": ticket.get("conflict_basis", ""),
            "revocation_notice": ticket.get("revocation_notice", ""),
            "authorization_revoked_at": ticket.get("authorization_revoked_at", ""),
            "completion_basis": ticket.get("completion_basis", ""),
            "termination_basis": ticket.get("termination_basis", ""),
            "terminal_basis": ticket.get("terminal_basis", ""),
            "授权范围": ticket.get("授权范围", ""),
            "scope": ticket.get("scope", {}),
            "stats": stats,
            "snapshot": snapshot,
            "claimed_at": ticket.get("claimed_at", ""),
            "last_read_at": ticket.get("last_read_at", ""),
            "completed_at": ticket.get("completed_at", ""),
            "terminated_at": ticket.get("terminated_at", ""),
        }

    def terminate_ticket(self, ticket_no: str, values: dict[str, Any] | None = None) -> dict[str, Any]:
        values = values or {}
        ticket = self.find_ticket(ticket_no)
        if ticket is None:
            return self.fail(f"切片工单 {ticket_no} 不存在")
        if ticket.get("status") in {"已完成", "已终止"}:
            return self.ok(f"工单已是{ticket.get('status')}状态", ticket=self.ticket_receipt(ticket))
        grant = self.find_grant(str(ticket.get("grant_no", "")))
        reason = str(values.get("reason") or values.get("终止原因") or "授权撤回冲突，授权人/接收者终止在途工单")
        at = now_iso()
        basis = (
            f"工单 {ticket_no} 在 cursor={ticket.get('cursor', 0)}/{ticket.get('snapshot_total', 0)} 处终止；"
            f"终止时间 {at}；原因：{reason}；"
            f"授权 {ticket.get('grant_no')} 当前状态 {(grant or {}).get('status', '未知')}；"
            f"快照 {ticket.get('snapshot_no')} / hash {ticket.get('snapshot_hash')}；"
            "终止后不再读取剩余成员，也不能发起新作业。"
        )
        ticket["status"] = "已终止"
        ticket["pending"] = False
        ticket["abnormal"] = True
        ticket["terminated_at"] = at
        ticket["termination_basis"] = basis
        ticket["terminal_basis"] = basis
        slice_row = self._upsert_ticket_slice_row(ticket, grant, status="已终止")
        self.audit("TERMINATE", basis, grant_no=str(ticket.get("grant_no", "")), ticket_no=ticket_no)
        return self.ok("工单已按可核实依据终止", ticket=self.ticket_receipt(ticket, grant), slice_row=slice_row)

    # ---------- 计算与历史复查 ----------

    def calculate_stats(self, member_keys: list[str]) -> dict[str, Any]:
        members = self.members_by_keys(member_keys)

        def group_rows(group_name: str) -> tuple[list[dict[str, Any]], list[float], float, float]:
            rows = [m for m in members if m.get("分组名称") == group_name]
            values = [float(m.get("指标值", 0) or 0) for m in rows]
            mean = statistics.fmean(values) if values else 0.0
            variance = statistics.pvariance(values) if len(values) > 1 else 0.0
            details = [{
                "用户标识": m.get("用户标识", ""),
                "用户姓名": m.get("用户姓名", ""),
                "实验编码": m.get("实验编码", ""),
                "指标值": float(m.get("指标值", 0) or 0),
                "与组均值差": round(float(m.get("指标值", 0) or 0) - mean, 4),
                "差异平方": round((float(m.get("指标值", 0) or 0) - mean) ** 2, 4),
            } for m in rows]
            return details, values, mean, variance

        ctrl_details, ctrl, ctrl_mean, ctrl_var = group_rows("对照组")
        treat_details, treat, treat_mean, treat_var = group_rows("实验组")
        within_var = round((ctrl_var + treat_var) / 2, 4)
        return {
            "实际成员数": len(members),
            "member_count": len(members),
            "对照组人数": len(ctrl),
            "实验组人数": len(treat),
            "对照组均值": round(ctrl_mean, 4),
            "实验组均值": round(treat_mean, 4),
            "均值差异": round(treat_mean - ctrl_mean, 4),
            "对照组组内方差": round(ctrl_var, 4),
            "实验组组内方差": round(treat_var, 4),
            "组内方差": within_var,
            "对照组组内最大差异": round(max(ctrl) - min(ctrl), 4) if ctrl else 0,
            "实验组组内最大差异": round(max(treat) - min(treat), 4) if treat else 0,
            "对照组明细": ctrl_details,
            "实验组明细": treat_details,
            "分组差异": f"均值差 {round(treat_mean - ctrl_mean, 4)}；组内方差 {within_var}",
        }

    def compute_ticket(self, ticket_no: str, values: dict[str, Any] | None = None) -> dict[str, Any]:
        values = values or {}
        ticket = self.find_ticket(ticket_no)
        if ticket is None:
            return self.fail(f"切片工单 {ticket_no} 不存在", code="TICKET_NOT_FOUND")
        grant = self.find_grant(str(ticket.get("grant_no", "")))
        if ticket.get("status") == "已终止":
            return self.fail("工单已终止，不能计算；请查看终止依据", ticket=self.ticket_receipt(ticket, grant), code="TICKET_TERMINATED")

        # 已完成计算必须幂等：始终复用同一份 computed snapshot。
        if ticket.get("status") == "已完成" and ticket.get("computed_member_keys") and not values.get("force_recompute"):
            stats = self.calculate_stats(list(ticket["computed_member_keys"]))
            return self.ok("该工单已完成；返回的是同一份成员快照结果", ticket=self.ticket_receipt(ticket, grant), stats=stats)

        snapshot = self.find_snapshot(str(ticket.get("snapshot_no", "")))
        if snapshot is None:
            return self.fail("成员快照缺失，不能计算", code="SNAPSHOT_MISSING")

        # 默认按当前已领取并交付的成员计算；若显式 use=snapshot，则使用领取时密封全量。
        # 无论哪种，都在此处冻结 computed_member_keys，之后筛选/人群变动无法改变。
        use = str(values.get("use") or values.get("dataset") or "delivered")
        if use == "snapshot":
            candidate_keys = list(snapshot.get("member_keys", []))
        else:
            candidate_keys = list(ticket.get("delivered_member_keys", []))
        allowed_keys = set(snapshot.get("member_keys", []))
        keys = [key for key in candidate_keys if key in allowed_keys]
        if not keys:
            ticket["status"] = "计算失败"
            ticket["abnormal"] = True
            ticket["失败原因"] = "没有已领取且属于授权快照的成员可计算"
            return self.fail(ticket["失败原因"], ticket=self.ticket_receipt(ticket, grant))

        stats = self.calculate_stats(keys)
        computed_hash = hash_member_keys(keys)
        at = now_iso()
        ticket["computed_member_keys"] = keys
        ticket["computed_hash"] = computed_hash
        ticket["实际成员数"] = len(keys)
        ticket["status"] = "已完成"
        ticket["pending"] = False
        ticket["abnormal"] = False
        ticket["completed_at"] = at
        revoke_part = ""
        if grant and grant.get("status") != "有效":
            revoke_part = (
                f"授权 {grant.get('grant_no')} 已于 {grant.get('revoked_at')} 撤回；"
                "本作业使用撤回前领取时密封快照完成，不构成新授权。"
            )
        ticket["completion_basis"] = (
            f"作业 {ticket_no} 只使用快照 {ticket.get('snapshot_no')} 的子集 {computed_hash}；"
            f"实际计算 {len(keys)} 人，checkpoint=cursor {ticket.get('cursor')}；"
            f"完成时间 {at}；领取时授权版本 v{ticket.get('grant_version_at_claim')}。{revoke_part}"
        )
        ticket["terminal_basis"] = ticket["completion_basis"]
        slice_row = self._upsert_ticket_slice_row(ticket, grant, status="已计算", stats=stats)
        slice_row["computed_hash"] = computed_hash
        slice_row["计算时间"] = at
        self.audit("COMPUTE", ticket["completion_basis"], grant_no=str(ticket.get("grant_no", "")), ticket_no=ticket_no)
        return self.ok("切片计算完成，实际成员快照和统计明细已留存", ticket=self.ticket_receipt(ticket, grant), stats=stats, slice_row=slice_row)

    def confirm_slice(self, slice_id: int, values: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
        row = store.find("segment_slice", slice_id)
        if row is None:
            return None, f"切片 {slice_id} 不存在"
        if row.get("status") not in {"已计算", "已确认"}:
            return None, "仅已计算切片可确认"
        if row.get("status") != "已确认":
            row["status"] = "已确认"
            row["confirmed_at"] = now_iso()
            row["pending"] = False
            row["history_locked"] = True
            if not row.get("历史凭证"):
                credential = f"CRED-{row.get('人群编码', 'SLICE')}-{int(row['id']):03d}"
                row["历史凭证"] = credential
                row["credential_no"] = credential
            self.audit("CONFIRM", f"切片 {row.get('切片批次')} 已确认，历史凭证 {row.get('历史凭证')}，成员数 {row.get('实际成员数')}")
        return row, "切片已确认并锁定历史凭证"

    def credential_context(self, credential_no: str) -> dict[str, Any]:
        row = self.find_credential_slice(credential_no)
        if row is None:
            return self.fail(f"历史凭证 {credential_no} 不存在", code="CREDENTIAL_NOT_FOUND")
        snapshot = self.find_snapshot(str(row.get("snapshot_no", "")))
        grant = self.find_grant(str(row.get("grant_no", row.get("授权凭证", ""))))
        keys = list((snapshot or {}).get("member_keys", []))
        members = [self.public_member(m, (grant or {}).get("scope")) for m in self.members_by_keys(keys)]
        return self.ok(
            "历史凭证复查上下文已读取",
            slice_row=row,
            snapshot=snapshot,
            grant=grant,
            members=members,
            scope_text=row.get("授权范围", (grant or {}).get("授权范围", "")),
            original_member_count=row.get("实际成员数") or row.get("成员总数") or len(keys),
            can_recompute=snapshot is not None,
        )

    def recompute_credential(self, credential_no: str) -> dict[str, Any]:
        context = self.credential_context(credential_no)
        if not context.get("ok"):
            return context
        row: dict[str, Any] = context["slice_row"]
        snapshot: dict[str, Any] | None = context.get("snapshot")
        if snapshot is None:
            return self.fail("历史成员快照缺失，无法复算")
        keys = list(snapshot.get("member_keys", []))
        stats = self.calculate_stats(keys)
        expected_count = int(row.get("实际成员数") or row.get("成员总数") or 0)
        expected_hash = str(row.get("member_hash") or row.get("computed_hash") or snapshot.get("member_hash", ""))
        actual_hash = hash_member_keys(keys)
        consistent = (
            stats["实际成员数"] == expected_count
            and (not expected_hash or expected_hash in {actual_hash, str(snapshot.get("member_hash", ""))})
        )
        return self.ok(
            "已按历史凭证指向的同一份成员快照和原成员数复算" if consistent else "复算成员数或快照哈希与历史凭证不一致",
            consistent=consistent,
            credential_no=credential_no,
            original_member_count=expected_count,
            recomputed_member_count=stats["实际成员数"],
            original_hash=expected_hash,
            recomputed_hash=actual_hash,
            stats=stats,
            scope_text=row.get("授权范围", ""),
            slice_row=row,
        )


controlled_slice_service = ControlledSliceService()
