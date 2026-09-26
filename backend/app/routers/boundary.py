"""分包检测接口：维护分包记录，覆盖送样分包、回样接收、验收完成与批量补录回样。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.boundary import STATUS_ORDER, BoundaryService

router = APIRouter(prefix="/api/boundary", tags=["分包检测"])

service = BoundaryService()


class ReturnSampleBatch(BaseModel):
    """批量补录回样：每条只带分包编号与回样日期，逐条独立处理。"""

    items: list[dict[str, Any]] = Field(default_factory=list)


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按分包编号检索"),
    status: str | None = Query(default=None, description="待送样、分包中、已回样、已验收"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按分包编号与状态过滤分包检测列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STATUS_ORDER:
        raise HTTPException(status_code=400, detail=f"状态「{status}」不在允许的状态序列里")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/summary")
def summary() -> dict[str, int]:
    """各进度状态的记录数，给列表页统计卡片用，口径与列表一致。"""
    return service.summary()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出分包检测清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "boundary", "total": total, "items": items}


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条分包记录，缺字段或编号重复时说明原因而不是静默丢弃。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/return-samples")
def register_return_samples(payload: ReturnSampleBatch) -> dict[str, Any]:
    """批量补录回样：逐条按分包编号落回样日期，失败条目可单独重试。"""
    if not payload.items:
        raise HTTPException(status_code=400, detail="补录清单为空，请至少填写一条分包编号与回样日期")
    results, blocked = service.register_returns(payload.items)
    ok = not blocked and all(item["ok"] for item in results)
    message = "全部回样补录成功" if ok else f"部分回样补录被阻断：{'、'.join(blocked)}"
    return {"ok": ok, "message": message, "results": results, "blocked": blocked}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条分包记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"分包记录 {entry_id} 不存在或已归档")
    return entry


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条分包记录执行送样分包、回样接收、验收完成；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
