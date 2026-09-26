"""分包检测业务规则：送样、回样、验收三段数据分开存放，进度统一由三段记录推导。

- 回样日期只通过分包编号定位记录，不会串到别的分包编号上；
- 分包项目为空的记录不允许登记回样，并说明原因；
- 已验收的记录回样日期锁定，不允许再改；
- 新增记录的分包编号查重，历史分包记录不会被覆盖。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "boundary"
REQUIRED_FIELDS = ["分包编号", "分包原因", "分包方名称", "分包项目"]
STATUS_ORDER = ["待送样", "分包中", "已回样", "已验收"]
ACTIONS = ["送样分包", "回样接收", "验收完成"]


def _today() -> str:
    return date.today().isoformat()


def derive_status(entry: dict[str, Any]) -> str:
    """进度只认三段阶段记录：验收 > 回样 > 送样，列表、详情、验收弹窗同一份口径。"""
    if entry["acceptance"].get("验收日期"):
        return "已验收"
    if entry["receipt"].get("回样日期"):
        return "已回样"
    if entry["dispatch"].get("送样日期"):
        return "分包中"
    return "待送样"


def serialize(entry: dict[str, Any]) -> dict[str, Any]:
    """把三段阶段记录摊平成列表/详情共用的视图，阶段明细一并带出。"""
    status = derive_status(entry)
    return {
        "id": entry["id"],
        "分包编号": entry.get("分包编号"),
        "分包原因": entry.get("分包原因"),
        "分包方名称": entry.get("分包方名称"),
        "资质编号": entry.get("资质编号"),
        "分包项目": entry.get("分包项目"),
        "送样日期": entry["dispatch"].get("送样日期"),
        "回样日期": entry["receipt"].get("回样日期"),
        "验收日期": entry["acceptance"].get("验收日期"),
        "验收结论": entry["acceptance"].get("验收结论"),
        "status": status,
        "分包状态": status,
        "stages": {
            "送样": dict(entry["dispatch"]),
            "回样": dict(entry["receipt"]),
            "验收": dict(entry["acceptance"]),
        },
        "pending": status != STATUS_ORDER[-1],
        "abnormal": bool(entry.get("abnormal")),
    }


class BoundaryService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("分包编号", ""))]
        if status:
            rows = [row for row in rows if derive_status(row) == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [serialize(row) for row in rows[start:start + size]], total

    def summary(self) -> dict[str, int]:
        """各状态记录数：列表页统计卡片与列表本身用同一个 derive_status。"""
        counts = {status: 0 for status in STATUS_ORDER}
        for row in store.rows(MODULE):
            counts[derive_status(row)] += 1
        return counts

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return serialize(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}（分包项目为空时不允许提交）"
        code = str(values["分包编号"]).strip()
        if self._find_by_code(code) is not None:
            return None, f"分包编号 {code} 已存在，新增不能覆盖历史分包记录"
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "分包编号": code,
            "分包原因": str(values["分包原因"]).strip(),
            "分包方名称": str(values["分包方名称"]).strip(),
            "资质编号": str(values.get("资质编号") or "").strip(),
            "分包项目": str(values["分包项目"]).strip(),
            "dispatch": {"送样日期": None},
            "receipt": {"回样日期": None},
            "acceptance": {"验收日期": None, "验收结论": None},
            "pending": True,
            "abnormal": False,
        }
        rows.append(entry)
        return serialize(entry), "分包记录已登记"

    def run_action(self, entry_id: int, action: str, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"分包记录 {entry_id} 不存在或已归档"
        status = derive_status(entry)
        if action == "送样分包":
            if status != "待送样":
                return None, f"当前进度为「{status}」，不能重复送样分包"
            send_date = str(values.get("送样日期") or "").strip() or _today()
            entry["dispatch"]["送样日期"] = send_date
            self._sync_flags(entry)
            return serialize(entry), f"分包记录已送样分包，送样日期 {send_date}"
        if action == "回样接收":
            ok, message = self._register_return(entry, str(values.get("回样日期") or "").strip())
            if not ok:
                return None, message
            self._sync_flags(entry)
            return serialize(entry), message
        if action == "验收完成":
            if status == "已验收":
                return None, "该分包记录已验收，不允许重复验收"
            if status != "已回样":
                return None, f"当前进度为「{status}」，需先登记回样再验收"
            accept_date = str(values.get("验收日期") or "").strip() or _today()
            entry["acceptance"]["验收日期"] = accept_date
            entry["acceptance"]["验收结论"] = str(values.get("验收结论") or "").strip() or "合格"
            self._sync_flags(entry)
            return serialize(entry), f"分包记录已验收完成，验收日期 {accept_date}"
        return None, f"动作「{action}」不属于分包检测可执行范围"

    def register_returns(self, items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        """批量补录回样：逐条按分包编号定位，互不影响；被阻断的编号单独汇总。"""
        results: list[dict[str, Any]] = []
        blocked: list[str] = []
        for item in items:
            code = str(item.get("分包编号") or "").strip()
            return_date = str(item.get("回样日期") or "").strip()
            if not code:
                results.append({"分包编号": "", "ok": False, "message": "分包编号为空，无法定位回样记录"})
                continue
            entry = self._find_by_code(code)
            if entry is None:
                message = f"分包编号 {code} 不存在，回样日期不会落到其他编号上"
                results.append({"分包编号": code, "ok": False, "message": message})
                blocked.append(code)
                continue
            ok, message = self._register_return(entry, return_date)
            if ok:
                self._sync_flags(entry)
            else:
                blocked.append(code)
            results.append({"分包编号": code, "ok": ok, "message": message})
        return results, blocked

    def _register_return(self, entry: dict[str, Any], return_date: str) -> tuple[bool, str]:
        """回样登记的唯一入口：单条动作与批量补录走同一套校验。"""
        code = str(entry.get("分包编号") or "")
        if not str(entry.get("分包项目") or "").strip():
            return False, f"分包编号 {code} 的分包项目为空，不允许登记回样，请先补全分包项目"
        status = derive_status(entry)
        if status == "已验收":
            return False, f"分包编号 {code} 已验收，回样日期已锁定，不允许再改"
        if status == "待送样":
            return False, f"分包编号 {code} 尚未送样分包，不能登记回样"
        if not return_date:
            return False, f"分包编号 {code} 未填写回样日期"
        send_date = entry["dispatch"].get("送样日期")
        if send_date and return_date < send_date:
            return False, f"分包编号 {code} 的回样日期 {return_date} 早于送样日期 {send_date}，与送样记录对不上"
        entry["receipt"]["回样日期"] = return_date
        return True, f"分包编号 {code} 回样已登记，回样日期 {return_date}"

    def _find_by_code(self, code: str) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if str(row.get("分包编号", "")).strip() == code:
                return row
        return None

    def _sync_flags(self, entry: dict[str, Any]) -> None:
        entry["pending"] = derive_status(entry) != STATUS_ORDER[-1]
