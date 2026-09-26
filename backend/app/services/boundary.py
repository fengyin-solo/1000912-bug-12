"""分包检测业务规则：送样、回样、验收三段数据分开存放，状态由三段进度唯一派生。

存储结构（内存仓库中的一条分包记录）::

    {
        "id": 1,
        "分包编号": "BOUN-0001", "分包原因": ..., "分包方名称": ...,
        "资质编号": ..., "分包项目": ...,
        "stages": {
            "送样": {"date": "2026-09-01"},
            "回样": {"date": "2026-09-12"},
            "验收": {"date": "2026-09-15"},
        },
        "abnormal": False,
    }

回样日期只登记在「对应分包编号那条记录」的 stages["回样"] 里，
验收动作只写 stages["验收"]，任何动作都不会覆盖另一段的数据。
对外（列表/详情/导出）统一经 serialize_entry 投影成含「送样日期/回样日期/
验收日期/分包状态」的扁平结构，三处页面看到的进度口径完全一致。
"""
from __future__ import annotations

import copy
from typing import Any

from app.store import store

MODULE = "boundary"

# 登记分包记录时必须提供的基础字段
REQUIRED_FIELDS = ["分包编号", "分包原因", "分包方名称", "资质编号", "分包项目"]
BASE_FIELDS = REQUIRED_FIELDS

# 三段进度按顺序排列，状态由三段数据派生，不再允许动作直接写状态
STAGE_ORDER = ["送样", "回样", "验收"]
STATUS_BY_STAGE: dict[str | None, str] = {
    None: "待送样",
    "送样": "分包中",
    "回样": "已回样",
    "验收": "已验收",
}
STATUS_ORDER = ["待送样", "分包中", "已回样", "已验收"]


class BoundaryService:
    # ---------- 读取 ----------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self.serialize_entry(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("分包编号", ""))]
        if status:
            rows = [row for row in rows if row.get("分包状态") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return self.serialize_entry(row) if row is not None else None

    # ---------- 登记 ----------
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}，请补全后再提交"

        code = str(values["分包编号"]).strip()
        # 分包编号是回样/验收数据落位的唯一锚点，重复编号会导致历史记录被顶替
        if any(str(row.get("分包编号", "")).strip() == code for row in store.rows(MODULE)):
            return None, f"分包编号 {code} 已存在，重复登记会覆盖历史分包记录，请核对编号"

        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in BASE_FIELDS:
            entry[field] = str(values[field]).strip()
        # 三段数据分开初始化，互不挤占
        entry["stages"] = {stage: {} for stage in STAGE_ORDER}
        entry["abnormal"] = False
        rows.append(entry)
        self._sync_cache(entry)
        return self.serialize_entry(entry), None

    # ---------- 送样 ----------
    def dispatch(
        self, entry_id: int, send_date: str | None
    ) -> tuple[dict[str, Any] | None, str | None]:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None, f"分包记录 {entry_id} 不存在或已归档"
        date = (send_date or "").strip()
        if not date:
            return None, "送样日期不能为空，请填写后再提交"
        stages = row.setdefault("stages", {s: {} for s in STAGE_ORDER})
        if "送样" in stages and stages["送样"].get("date"):
            return None, f"分包编号 {row.get('分包编号')} 已送样，送样日期不允许重复登记"
        # 只写送样这一段，不触碰回样/验收
        stages["送样"] = {"date": date}
        self._sync_cache(row)
        return self.serialize_entry(row), None

    # ---------- 回样（单条 / 批量补录） ----------
    def register_return(
        self,
        entry_id: int,
        return_date: str | None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None, f"分包记录 {entry_id} 不存在或已归档"
        date = (return_date or "").strip()
        if not date:
            return None, "回样日期不能为空，请填写后再提交"
        if not str(row.get("分包项目") or "").strip():
            # 阻断时把具体分包编号带出来，方便业务核对
            return None, f"分包编号 {row.get('分包编号')} 的分包项目为空，无法核对回样内容，补全分包项目后才允许登记回样"

        stages = row.setdefault("stages", {s: {} for s in STAGE_ORDER})
        latest = self._latest_stage(stages)
        if latest is None:
            return None, f"分包编号 {row.get('分包编号')} 尚未送样（当前进度：{self._status(stages)}），请先完成送样分包再登记回样"
        if latest == "验收":
            return None, f"分包编号 {row.get('分包编号')} 当前进度为「已验收」，已验收的记录不允许再修改回样日期"

        # 只更新回样这一段：验收日期保留不动，送样日期也不受影响
        stages["回样"] = {"date": date}
        self._sync_cache(row)
        return self.serialize_entry(row), None

    def register_return_batch(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """批量补录回样：逐条独立处理，单条失败不影响其他记录，前端可只重试失败的那一条。"""
        results: list[dict[str, Any]] = []
        for item in items:
            entry_id = item.get("id")
            try:
                entry_id = int(entry_id)
            except (TypeError, ValueError):
                results.append({"id": entry_id, "ok": False, "message": "分包记录编号无效"})
                continue
            entry, error = self.register_return(entry_id, item.get("回样日期"))
            results.append({
                "id": entry_id,
                "ok": entry is not None,
                "message": f"分包编号 {entry['分包编号']} 回样日期已登记" if entry else (error or ""),
                "entry": entry,
            })
        return results

    # ---------- 验收 ----------
    def accept(
        self, entry_id: int, accept_date: str | None
    ) -> tuple[dict[str, Any] | None, str | None]:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None, f"分包记录 {entry_id} 不存在或已归档"
        date = (accept_date or "").strip()
        if not date:
            return None, "验收日期不能为空，请填写后再提交"

        stages = row.setdefault("stages", {s: {} for s in STAGE_ORDER})
        latest = self._latest_stage(stages)
        if latest == "验收":
            return None, f"分包编号 {row.get('分包编号')} 已验收完成，不能重复验收"
        if latest != "回样":
            return None, (
                f"分包编号 {row.get('分包编号')} 尚未登记回样（当前进度：{self._status(stages)}），"
                "请先完成回样接收再验收"
            )

        # 只写验收这一段：回样日期原样保留，验收后不会再丢失
        stages["验收"] = {"date": date}
        row["abnormal"] = False
        self._sync_cache(row)
        return self.serialize_entry(row), None

    # ---------- 投影：三处页面共用同一份口径 ----------
    @staticmethod
    def _latest_stage(stages: dict[str, Any]) -> str | None:
        latest: str | None = None
        for stage in STAGE_ORDER:
            if isinstance(stages.get(stage), dict) and stages[stage].get("date"):
                latest = stage
        return latest

    def _status(self, stages: dict[str, Any]) -> str:
        return STATUS_BY_STAGE[self._latest_stage(stages)]

    def _sync_cache(self, row: dict[str, Any]) -> None:
        """把派生状态回写到原始行，供 store.overview 等通用入口直接计数。"""
        stages = row.get("stages")
        if not isinstance(stages, dict):
            stages = {s: {} for s in STAGE_ORDER}
            row["stages"] = stages
        status = STATUS_BY_STAGE[self._latest_stage(stages)]
        row["status"] = status
        row["pending"] = status != STATUS_ORDER[-1]

    def serialize_entry(self, row: dict[str, Any]) -> dict[str, Any]:
        """把分段存储的记录投影成列表/详情/导出统一使用的扁平字段。"""
        stages = row.get("stages")
        if not isinstance(stages, dict):
            # 兼容早期可能没有 stages 的记录
            stages = {s: {} for s in STAGE_ORDER}
            row["stages"] = stages
        status = STATUS_BY_STAGE[self._latest_stage(stages)]
        # 同步派生状态到原始行，保证 store.overview 等通用入口计数正确
        row["status"] = status
        row["pending"] = status != STATUS_ORDER[-1]

        entry = copy.deepcopy(row)
        entry["送样日期"] = (stages.get("送样") or {}).get("date")
        entry["回样日期"] = (stages.get("回样") or {}).get("date")
        entry["验收日期"] = (stages.get("验收") or {}).get("date")
        entry["分包状态"] = status
        return entry
