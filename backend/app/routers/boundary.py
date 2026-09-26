"""分包检测接口：送样分包、回样登记、验收完成三段分开提交，互不覆盖。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.boundary import STATUS_ORDER, BoundaryService

router = APIRouter(prefix="/api/boundary", tags=["分包检测"])

service = BoundaryService()

LIST_FIELDS = ["分包编号", "分包原因", "分包方名称", "资质编号", "分包项目", "送样日期", "回样日期", "验收日期", "分包状态"]
STATUSES = STATUS_ORDER


class StagePayload(BaseModel):
    """送样 / 验收动作用：只需提交对应阶段的日期。"""

    date: str | None = None


class ReturnItem(BaseModel):
    """批量补录回样中的一条：日期只落在该 id 对应的分包编号上。"""

    id: int
    回样日期: str | None = None


class ReturnBatchPayload(BaseModel):
    items: list[ReturnItem] = Field(default_factory=list)


class BatchResult(BaseModel):
    ok: bool
    message: str
    results: list[dict[str, Any]]


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
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出分包检测清单：返回当前数据的全量投影，字段与列表完全一致。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "boundary", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条分包记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"分包记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条分包记录，缺字段时说明原因而不是静默丢弃。"""
    entry, error = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=error or "分包记录登记失败")
    return ActionResult(ok=True, message="分包记录已登记", entry=entry)


@router.post("/{entry_id}/dispatch", response_model=ActionResult)
def dispatch_entry(entry_id: int, payload: StagePayload) -> ActionResult:
    """送样分包：只登记送样日期，进度推进到分包中。"""
    entry, error = service.dispatch(entry_id, payload.date)
    if entry is None:
        return ActionResult(ok=False, message=error or "送样分包失败")
    return ActionResult(ok=True, message=f"分包编号 {entry['分包编号']} 已送样", entry=entry)


@router.post("/{entry_id}/return", response_model=ActionResult)
def register_return(entry_id: int, payload: ReturnItem) -> ActionResult:
    """回样登记：回样日期只写在该分包编号上；已验收的记录禁止修改。"""
    entry, error = service.register_return(entry_id, payload.回样日期)
    if entry is None:
        return ActionResult(ok=False, message=error or "回样登记失败")
    return ActionResult(ok=True, message=f"分包编号 {entry['分包编号']} 回样已登记", entry=entry)


@router.post("/returns/batch", response_model=BatchResult)
def register_return_batch(payload: ReturnBatchPayload) -> BatchResult:
    """批量补录回样：逐条返回成功/失败原因，失败的记录可单独重试。"""
    raw_items = [item.model_dump() for item in payload.items]
    results = service.register_return_batch(raw_items)
    failed = [item for item in results if not item["ok"]]
    if failed:
        codes = "、".join(str(item.get("message", "")) for item in failed)
        message = f"{len(failed)} 条回样补录被阻断：{codes}"
    else:
        message = f"{len(results)} 条回样全部登记完成"
    return BatchResult(ok=not failed, message=message, results=results)


@router.post("/{entry_id}/accept", response_model=ActionResult)
def accept_entry(entry_id: int, payload: StagePayload) -> ActionResult:
    """验收完成：只登记验收日期，回样日期原样保留，验收后锁死回样。"""
    entry, error = service.accept(entry_id, payload.date)
    if entry is None:
        return ActionResult(ok=False, message=error or "验收完成失败")
    return ActionResult(ok=True, message=f"分包编号 {entry['分包编号']} 已验收完成", entry=entry)
