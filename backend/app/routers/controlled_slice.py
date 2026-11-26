"""受控切片专用接口：共享申请、授权、工单领取/续读/计算、历史凭证复查。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from app.services.controlled_slice import controlled_slice_service as svc

router = APIRouter(prefix="/api/controlled-slices", tags=["受控切片"])


async def _payload(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


@router.get("/cohorts/{cohort_code}/detail")
def cohort_detail_by_code(cohort_code: str) -> dict[str, Any]:
    return svc.cohort_detail(code=cohort_code)


@router.post("/cohorts/{cohort_code}/share-requests")
async def create_share_request(cohort_code: str, request: Request) -> dict[str, Any]:
    cohort = svc.find_cohort(code=cohort_code)
    if cohort is None:
        return {"ok": False, "message": f"人群包 {cohort_code} 不存在"}
    values = await _payload(request)
    return svc.create_share_request(cohort, values)


@router.post("/cohorts/{cohort_code}/grants")
async def create_grant(cohort_code: str, request: Request) -> dict[str, Any]:
    cohort = svc.find_cohort(code=cohort_code)
    if cohort is None:
        return {"ok": False, "message": f"人群包 {cohort_code} 不存在"}
    values = await _payload(request)
    return svc.grant_eligibility(cohort, values)


@router.get("/grants")
def list_grants(recipient: str = Query(default=""), cohort_code: str = Query(default="")) -> dict[str, Any]:
    return svc.list_grants(recipient, cohort_code)


@router.get("/grants/{grant_no}")
def grant_context(grant_no: str, recipient: str = Query(default="")) -> dict[str, Any]:
    return svc.grant_context(grant_no, recipient)


@router.post("/grants/{grant_no}/open")
async def open_grant(grant_no: str, request: Request) -> dict[str, Any]:
    values = await _payload(request)
    recipient = str(values.get("recipient") or values.get("接收者") or "")
    return svc.grant_context(grant_no, recipient)


@router.post("/grants/{grant_no}/revoke")
async def revoke_grant(grant_no: str, request: Request) -> dict[str, Any]:
    values = await _payload(request)
    return svc.revoke_grant(grant_no, values)


@router.post("/grants/{grant_no}/tickets")
async def claim_ticket(grant_no: str, request: Request) -> dict[str, Any]:
    values = await _payload(request)
    return svc.claim_ticket(grant_no, values)


@router.get("/tickets/{ticket_no}")
def ticket_detail(ticket_no: str) -> dict[str, Any]:
    ticket = svc.find_ticket(ticket_no)
    if ticket is None:
        return {"ok": False, "message": f"切片工单 {ticket_no} 不存在"}
    return svc.ok("工单领用结果已读取", ticket=svc.ticket_receipt(ticket))


@router.post("/tickets/{ticket_no}/read")
async def read_ticket(ticket_no: str, request: Request) -> dict[str, Any]:
    values = await _payload(request)
    # 同时允许 query 参数传 keyword/name，模拟页面筛选；服务端仍只在快照内过滤。
    values.update({k: v for k, v in request.query_params.items() if k in {"keyword", "name", "batch_size", "size"}})
    return svc.read_ticket(ticket_no, values)


@router.get("/tickets/{ticket_no}/members")
def ticket_members(
    ticket_no: str,
    keyword: str = Query(default=""),
    name: str = Query(default=""),
) -> dict[str, Any]:
    return svc.read_ticket(ticket_no, {
        "advance": False,
        "keyword": keyword or name,
        "all_remaining": False,
        "batch_size": 0,
        "only_new": False,
    })


@router.post("/tickets/{ticket_no}/continue")
async def continue_ticket(ticket_no: str, request: Request) -> dict[str, Any]:
    values = await _payload(request)
    values["all_remaining"] = True
    values.setdefault("auto_compute", True)
    return svc.read_ticket(ticket_no, values)


@router.post("/tickets/{ticket_no}/terminate")
async def terminate_ticket(ticket_no: str, request: Request) -> dict[str, Any]:
    values = await _payload(request)
    return svc.terminate_ticket(ticket_no, values)


@router.post("/tickets/{ticket_no}/compute")
async def compute_ticket(ticket_no: str, request: Request) -> dict[str, Any]:
    values = await _payload(request)
    return svc.compute_ticket(ticket_no, values)


@router.get("/credentials/{credential_no}")
def credential_detail(credential_no: str) -> dict[str, Any]:
    return svc.credential_context(credential_no)


@router.post("/credentials/{credential_no}/recompute")
async def recompute_credential(credential_no: str) -> dict[str, Any]:
    return svc.recompute_credential(credential_no)
