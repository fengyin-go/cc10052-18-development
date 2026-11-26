"""受控切片能力的确定性示例数据。

这里构造需求中的 C10 场景：
- C10 已授权给另一个项目的分析员「甲」；
- 切片工单 T1 已领取并读取了前 6 名成员，但尚未读完全部 10 人；
- 另有一份已确认历史切片和历史凭证，可按原快照、原成员数复查；
- 「王敏」在另一实验 EXP-999 有同名用户，用于验证服务端按实验+稳定用户键隔离。
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def _iso(value: str) -> str:
    return value


def hash_keys(keys: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(keys)).encode("utf-8")).hexdigest()[:16]


def member_key(experiment_code: str, user_id: str) -> str:
    return f"{experiment_code}::{user_id}"


def install_controlled_seed(seed_rows: dict[str, list[dict[str, Any]]]) -> None:
    now = datetime.now(timezone.utc).isoformat()

    c10_members_spec = [
        ("U1001", "王敏", "对照组", 10),
        ("U1002", "李伟", "实验组", 16),
        ("U1003", "张娜", "对照组", 11),
        ("U1004", "刘洋", "实验组", 18),
        ("U1005", "陈静", "对照组", 9),
        ("U1006", "杨磊", "实验组", 15),
        ("U1007", "赵悦", "对照组", 12),
        ("U1008", "黄强", "实验组", 17),
        ("U1009", "周婷", "对照组", 8),
        ("U1010", "吴昊", "实验组", 14),
    ]
    members: list[dict[str, Any]] = []
    for idx, (user_id, name, group, metric) in enumerate(c10_members_spec, start=1):
        exp = "EXP-C10"
        members.append({
            "id": idx,
            "member_key": member_key(exp, user_id),
            "实验编码": exp,
            "用户标识": user_id,
            "用户姓名": name,
            "分组名称": group,
            "指标值": metric,
            "人群编码": "C10",
            "status": "在组",
        })

    # 同名/同标识但来自另一实验的用户；稳定 member_key 含实验前缀，绝不能并入 C10。
    members.append({
        "id": 11,
        "member_key": member_key("EXP-999", "U1001"),
        "实验编码": "EXP-999",
        "用户标识": "U1001",
        "用户姓名": "王敏",
        "分组名称": "对照组",
        "指标值": 99,
        "人群编码": "OTHER",
        "status": "在组",
    })

    all_keys = [str(row["member_key"]) for row in members if row["人群编码"] == "C10"]
    first_six_keys = all_keys[:6]
    snapshot_hash = hash_keys(all_keys)

    scope = {
        "人群编码": "C10",
        "实验编码": ["EXP-C10"],
        "可计算分组": ["对照组", "实验组"],
        "可读字段": ["用户标识", "用户姓名", "分组名称", "指标值"],
        "允许操作": ["读取授权成员", "领取切片工单", "计算组内成员差异", "生成切片统计"],
        "禁止事项": ["跨实验取数", "按同姓名扩圈", "修改筛选扩大范围", "撤回后创建新作业"],
    }
    scope_text = "实验 EXP-C10；仅 C10 快照成员；可读 用户标识/姓名/分组/指标值；允许组内差异计算；禁止跨实验、同姓名扩圈和筛选扩权"

    cohort_rows = seed_rows.setdefault("cohort_builder", [])
    cohort_rows.append({
        "id": max((int(r.get("id", 0)) for r in cohort_rows), default=0) + 1,
        "status": "已生成",
        "pending": False,
        "abnormal": False,
        "人群编码": "C10",
        "成员组编码": "C10",
        "人群名称": "成员组 C10（高价值活跃成员）",
        "圈选条件": "实验 EXP-C10 近30天活跃且有曝光",
        "人群规模": str(len(all_keys)),
        "刷新周期": "每日 02:00",
        "归属项目": "北极星实验评估项目",
        "归属人": "数据工程组授权人",
        "包归属凭证": "OWN-C10-北极星",
        "来源实验": "EXP-C10",
        "成员总数": len(all_keys),
        "当前快照": "SNAP-C10-CONFIRMED",
        "共享状态": "已授权甲",
    })

    seed_rows["cohort_member"] = members

    seed_rows["cohort_share_request"] = [{
        "id": 1,
        "request_no": "REQ-C10-JIA",
        "cohort_id": 4,
        "人群编码": "C10",
        "接收者": "甲",
        "接收项目": "跨境增长分析项目",
        "申请范围": scope_text,
        "申请事由": "另一个项目的分析员需要交付受控切片样本",
        "status": "已授权",
        "申请时间": "2026-11-20T09:50:00+00:00",
    }]

    seed_rows["cohort_grant"] = [{
        "id": 1,
        "grant_no": "GRANT-C10-JIA",
        "request_no": "REQ-C10-JIA",
        "cohort_id": 4,
        "人群编码": "C10",
        "归属项目": "北极星实验评估项目",
        "归属人": "数据工程组授权人",
        "包归属凭证": "OWN-C10-北极星",
        "接收者": "甲",
        "接收项目": "跨境增长分析项目",
        "scope": scope,
        "授权范围": scope_text,
        "status": "有效",
        "version": 1,
        "granted_at": "2026-11-20T10:00:00+00:00",
        "revoked_at": None,
        "revoke_reason": "",
        "ownership_verified": True,
        "receiver_verified": True,
    }]

    seed_rows["member_snapshot"] = [
        {
            "id": 1,
            "snapshot_no": "SNAP-C10-CONFIRMED",
            "人群编码": "C10",
            "cohort_code": "C10",
            "member_keys": all_keys,
            "member_count": len(all_keys),
            "member_hash": snapshot_hash,
            "sealed_at": "2026-11-20T10:05:00+00:00",
            "basis": "已确认历史切片计算前密封，后续人群刷新不改变该快照",
        },
        {
            "id": 2,
            "snapshot_no": "SNAP-C10-T1",
            "人群编码": "C10",
            "cohort_code": "C10",
            "member_keys": all_keys,
            "member_count": len(all_keys),
            "member_hash": snapshot_hash,
            "sealed_at": "2026-11-26T08:30:00+00:00",
            "basis": "工单 TKT-C10-JIA-001 领取时密封；所有续读和计算只能使用该快照",
        },
    ]

    slice_rows = seed_rows.setdefault("segment_slice", [])
    history_slice_id = max((int(r.get("id", 0)) for r in slice_rows), default=0) + 1
    slice_rows.append({
        "id": history_slice_id,
        "status": "已确认",
        "pending": False,
        "abnormal": False,
        "切片批次": "SLICE-C10-CONFIRMED-001",
        "实验编码": "EXP-C10",
        "切片维度": "授权人群",
        "切片值": "C10 / 甲",
        "分组差异": "均值差 6.0；组内方差 2.0",
        "切片条件": "C10",
        "人群编码": "C10",
        "grant_no": "GRANT-C10-JIA",
        "授权凭证": "GRANT-C10-JIA",
        "历史凭证": "CRED-C10-HIST-001",
        "credential_no": "CRED-C10-HIST-001",
        "snapshot_no": "SNAP-C10-CONFIRMED",
        "授权范围": scope_text,
        "实际成员数": 10,
        "成员总数": 10,
        "member_count": 10,
        "member_hash": snapshot_hash,
        "对照组人数": 5,
        "实验组人数": 5,
        "对照组均值": 10.0,
        "实验组均值": 16.0,
        "均值差异": 6.0,
        "组内方差": 2.0,
        "确认时间": "2026-11-20T10:20:00+00:00",
        "history_locked": True,
    })

    ticket_slice_id = history_slice_id + 1
    scope_text_seed = scope_text
    slice_rows.append({
        "id": ticket_slice_id,
        "status": "计算中",
        "pending": True,
        "abnormal": False,
        "切片批次": "SLICE-C10-T1",
        "实验编码": "EXP-C10",
        "切片维度": "授权人群",
        "切片值": "C10 / 甲",
        "分组差异": "",
        "切片条件": "C10",
        "人群编码": "C10",
        "ticket_no": "TKT-C10-JIA-001",
        "grant_no": "GRANT-C10-JIA",
        "授权凭证": "GRANT-C10-JIA",
        "snapshot_no": "SNAP-C10-T1",
        "授权范围": scope_text_seed,
        "实际成员数": 0,
        "成员总数": 10,
        "member_count": 0,
    })

    seed_rows["slice_ticket"] = [{
        "id": 1,
        "ticket_no": "TKT-C10-JIA-001",
        "slice_batch": "SLICE-C10-T1",
        "segment_slice_id": ticket_slice_id,
        "grant_no": "GRANT-C10-JIA",
        "grant_version_at_claim": 1,
        "人群编码": "C10",
        "recipient": "甲",
        "接收者": "甲",
        "snapshot_no": "SNAP-C10-T1",
        "snapshot_hash": snapshot_hash,
        "snapshot_total": len(all_keys),
        "delivered_member_keys": first_six_keys,
        "read_count": len(first_six_keys),
        "cursor": len(first_six_keys),
        "checkpoint_cursor": len(first_six_keys),
        "实际成员数": 0,
        "status": "计算中",
        "pending": True,
        "abnormal": False,
        "claimed_at": "2026-11-26T08:30:00+00:00",
        "last_read_at": "2026-11-26T08:33:00+00:00",
        "conflict": False,
        "terminal_basis": "",
        "completion_basis": "",
        "termination_basis": "",
        "scope": scope,
        "授权范围": scope_text,
    }]

    seed_rows["controlled_slice_audit"] = [
        {
            "id": 1,
            "at": "2026-11-20T10:00:00+00:00",
            "type": "GRANT",
            "grant_no": "GRANT-C10-JIA",
            "ticket_no": "",
            "message": "授权人核对 C10 归属（北极星实验评估项目）与接收者甲（跨境增长分析项目）后授予切片领用资格",
        },
        {
            "id": 2,
            "at": "2026-11-26T08:30:00+00:00",
            "type": "CLAIM",
            "grant_no": "GRANT-C10-JIA",
            "ticket_no": "TKT-C10-JIA-001",
            "message": "甲领取切片工单，密封 SNAP-C10-T1，共 10 名成员",
        },
        {
            "id": 3,
            "at": "2026-11-26T08:33:00+00:00",
            "type": "READ",
            "grant_no": "GRANT-C10-JIA",
            "ticket_no": "TKT-C10-JIA-001",
            "message": "已读取至 cursor=6；剩余 4 名成员尚未读取",
        },
    ]

    # 保持 now 被引用，便于后续扩展动态种子；当前时间戳固定以保证场景可复查。
    _ = now
