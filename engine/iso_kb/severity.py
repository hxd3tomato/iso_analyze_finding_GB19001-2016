"""严重程度判定（对应 30-nc-taxonomy.md §2.2 打分卡）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import config, lexicon

# 维度权重
WEIGHTS = {"scope": 0.25, "product": 0.30, "repeat": 0.20, "level": 0.15, "trace": 0.10}

# 条款层级先验：这些条款的问题天然更接近"放行/合规/体系有效性"
HIGH_RISK_CLAUSES = {
    "8.6", "8.7", "7.1.5.2", "9.2", "9.3", "9.3.1", "9.3.2", "9.3.3",
    "8.3.1", "8.3.4", "8.3.5", "8.3.6", "4.3", "8.2.4",
}

# 条款最低等级（体系性/认证有效性问题）
SEVERITY_FLOOR = {"4.3": "MAJOR"}

SIGNALS = {
    "scope": [
        (r"全公司|整个公司|所有部门|各车间|全厂|所有产线|全部人员|全体员工", 10),
        (r"撤销|撤并|合并|并入", 10),
        (r"多个部门|多批|批量|多台|多处|多个工位|多个|全部|均有|均未", 10),
        (r"[2-9]\s*个?工位|[2-9]\s*条线|[2-9]\s*把|[2-9]\s*台|[2-9]\s*批|[2-9]\s*项", 10),
        (r"([2-9]|[1-9]\d)\s*(份|件|个|次|处|人|家|起)", 10),
        (r"认证机构|监督审核|证书范围", 10),
        (r"单台|一台|一份|一处|个别|某工位|一名|少数", 0),
    ],
    "product": [
        (r"已交付|已发货|已流出|已放行|已出厂|客户端|已投产", 10),
        (r"代签|未检验|未经检验|未验证|虚假|补填|后补|补签|补一下|集中.{0,8}同一(日|天)|造假", 9),
        (r"召回|退货|索赔|批量不合格", 9),
        (r"不合格|超差|失效|投诉|损坏|客诉", 7),
        (r"作废版本|旧版|版本不一致|失准|参数超范围", 7),
        (r"丢失|灭失|损坏|故障|数据丢失", 7),
        (r"无版本锁定|无修改日志|无备份|无权限|权限失控", 9),
        (r"无影响|未影响|不影响|均可拦截", 0),
    ],
    "repeat": [
        (r"重复|再次|多次|屡次|同类问题|上年|上次|又发生|连续", 10),
        (r"从未|一直没有|长期|多年|三年|一直", 10),
        (r"均未|未回收|未更新|系统性|全部未", 9),
        (r"\d+\s*次", 10),
        (r"未备份|无备份|未演练", 9),
        (r"首次|初次|偶发", 0),
    ],
    "level": [
        (r"法规|法定|强制|特种设备|行政许可|召回|未通知认证机构", 10),
        (r"删减|不适用|认证范围", 9),
        (r"放行|交付|不合格品|校准|内审|管理评审|设计", 7),
    ],
    "trace": [
        (r"无法追溯|追溯断链|查不到|无任何记录|无记录|未记录|无法证明", 10),
        (r"缺失|未填写|空白|代签|未保留|未归档", 7),
    ],
}


@dataclass
class Severity:
    level: str
    score: int
    drivers: List[str] = field(default_factory=list)
    veto: Optional[str] = None
    dims: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"level": self.level, "score": self.score, "drivers": self.drivers,
                "veto": self.veto, "dimensions": self.dims}


def _dim_score(text: str, dim: str, clause: str) -> tuple:
    """返回 (0~10 分, 命中说明)。未命中任何信号时取中性 5 分。"""
    best, label = 5, ""
    for rx, val in SIGNALS[dim]:
        if re.search(rx, text):
            if val > best or (best == 5 and val != 5):
                best, label = val, rx
            if val == 0 and best == 5:
                best, label = 0, rx
    if dim == "level" and clause in HIGH_RISK_CLAUSES and best < 7:
        best, label = 7, "条款层级"
    return best, label


def assess(text: str, clause: str, history_hits: int = 0) -> Severity:
    dims, drivers = {}, []
    for dim in WEIGHTS:
        val, label = _dim_score(text, dim, clause)
        dims[dim] = val
        if label and val != 5:
            drivers.append(f"{dim}:{val}")

    total = sum(WEIGHTS[d] * dims[d] for d in WEIGHTS) * 10
    if history_hits >= 2:
        total += 5
        drivers.append("history:repeated")

    total = float(round(total))
    level = "MAJOR" if total >= config.SEV_MAJOR else ("MINOR" if total >= config.SEV_MINOR else "OBS")
    veto_clause, veto_reason = lexicon.matched_veto(text)
    veto = None
    if veto_reason:
        veto = veto_reason
        level = "MAJOR"
        total = max(total, 85)
        drivers.append(f"veto:{veto_reason}")

    floor = SEVERITY_FLOOR.get(clause)
    if floor == "MAJOR" and level != "MAJOR":
        level = "MAJOR"
        total = max(total, 75)
        drivers.append("floor:条款最低等级")

    return Severity(level=level, score=int(round(total)), drivers=drivers, veto=veto, dims=dims)
