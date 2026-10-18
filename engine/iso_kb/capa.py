"""整改建议生成（对应 51-retrieval-and-prompts.md 的 TPL-CAPA-01）。

策略：案例库优先（真实、具体） -> 条款模板兜底（保证任何条款都有可用建议）。
每段都必须给出：动作 / 责任岗位 / 时限 / 完成标志。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from .store import Case, Clause, Store
from .tokenizer import cosine, terms

# 条款 -> 主要程序文件（对应 41-procedures-catalog.md）
CLAUSE_PROCEDURE = {
    "4.1": ("P-02", "企业战略策划控制程序"), "4.2": ("P-02", "企业战略策划控制程序"),
    "4.3": ("P-03", "质量计划控制程序"), "4.4": ("P-03", "质量计划控制程序"),
    "5.2.1": ("P-01", "管理评审控制程序"), "5.3": ("P-01", "管理评审控制程序"),
    "6.1": ("P-03", "质量计划控制程序"), "6.2": ("P-02", "企业战略策划控制程序"),
    "6.3": ("P-03", "质量计划控制程序"),
    "7.1.3": ("P-17", "设备管理控制程序"), "7.1.4": ("P-15", "过程控制程序"),
    "7.1.5.2": ("P-21", "检验、测量和试验设备控制程序"),
    "7.2": ("P-27", "培训控制程序"), "7.3": ("P-27", "培训控制程序"),
    "7.5.1": ("P-08", "文件和资料控制程序"), "7.5.2": ("P-08", "文件和资料控制程序"),
    "7.5.3": ("P-08", "文件和资料控制程序"),
    "8.2.3": ("P-07", "合同评审控制程序"), "8.2.4": ("P-07", "合同评审控制程序"),
    "8.3.4": ("P-04", "产品初期质量策划控制程序"), "8.3.6": ("P-04", "产品初期质量策划控制程序"),
    "8.4.1": ("P-11", "供应商选择和评定控制程序"), "8.4.3": ("P-10", "采购控制程序"),
    "8.5.1": ("P-15", "过程控制程序"), "8.5.2": ("P-14", "产品标识和可追溯性控制程序"),
    "8.5.4": ("P-15", "过程控制程序"), "8.5.6": ("P-15", "过程控制程序"),
    "8.6": ("P-20", "最终检验控制程序"), "8.7": ("P-23", "不合格品控制程序"),
    "9.1.2": ("P-28", "服务控制程序"), "9.1.3": ("P-29", "统计技术控制程序"),
    "9.2": ("P-26", "内部审核控制程序"), "9.3.1": ("P-01", "管理评审控制程序"),
    "10.2": ("P-24", "纠正和预防控制程序"),
}

DEFAULT_TIMELINE = {"MAJOR": ("7 个工作日", "30 个自然日"), "MINOR": ("10 个工作日", "60 个自然日"),
                    "OBS": ("15 个工作日", "90 个自然日")}

DIMENSION_LABEL = {"scope": "影响范围", "product": "产品符合性", "repeat": "重复性",
                   "level": "要求层级", "trace": "可追溯性"}


@dataclass
class CapaPlan:
    correction: str
    corrective_actions: List[str]
    verification: List[str]
    owner_suggestion: str
    timeline: dict
    horizontal_check: List[str]
    documents_to_update: List[str]
    source: str = "clause_template"

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_case_capa(raw: str) -> tuple:
    """把案例库里的"纠正—…；纠正措施—…；验证—…"拆成三段。"""
    if not raw:
        return "", [], []
    parts = re.split(r"[；;]\s*(?=纠正措施|验证|纠正)", raw)
    correction, corrective, verification = "", [], []
    for p in parts:
        p = p.strip("。 ")
        if p.startswith("纠正措施"):
            items = re.split(r"[，,、]|以及", p.replace("纠正措施—", "").replace("纠正措施-", ""))
            corrective = [i.strip("。 ") for i in items if len(i.strip()) > 3]
        elif p.startswith("验证"):
            items = re.split(r"[，,、]|以及", p.replace("验证—", "").replace("验证-", ""))
            verification = [i.strip("。 ") for i in items if len(i.strip()) > 2]
        elif p.startswith("纠正"):
            correction = p.replace("纠正—", "").replace("纠正-", "").strip("。 ")
    return correction, corrective, verification


def _best_case(clause: str, text: str, store: Store) -> Optional[Case]:
    best, best_s = None, 0.0
    q = terms(text)
    for c in store.cases_of(clause):
        s = cosine(q, c.doc_terms, store.idf)
        if s > best_s:
            best, best_s = c, s
    return best


def suggest(clause: str, severity: str, text: str, store: Store,
            doc_ref: str = "") -> CapaPlan:
    cl: Optional[Clause] = store.clause(clause)
    case = _best_case(clause, text, store)
    proc_id, proc_name = CLAUSE_PROCEDURE.get(clause, ("", ""))
    fast, slow = DEFAULT_TIMELINE.get(severity, DEFAULT_TIMELINE["MINOR"])

    correction, corrective, verification = "", [], []
    source = "clause_template"
    if case:
        c_corr, c_act, c_ver = _parse_case_capa(case.capa_raw)
        if c_corr or c_act:
            correction, corrective, verification = c_corr, c_act, c_ver
            source = f"case:{case.id}"
        elif case.capa_raw:
            correction = case.capa_raw
            source = f"case:{case.id}(部分)"

    title = cl.title if cl else clause
    if not correction:
        correction = f"立即纠正已发现的问题（{title}）：停用/隔离不合格对象、换发有效版本或补齐缺失记录，并评估受影响批次"
    if not corrective:
        corrective = [f"修订并落实《{proc_name or '相关程序'}》中 {clause} 的控制要求，明确责任人、频次与记录",
                      f"建立 {title} 的检查清单，纳入月度自查与内审必查项"]
    if not verification:
        verification = [f"连续 2 个检查周期（或 3 个批次）{title} 相关记录齐全且符合要求",
                        "内审/专项检查未再发现同类问题"]

    docs = []
    if proc_id:
        docs.append(f"{proc_id}《{proc_name}》")
    if cl:
        docs.append(f"手册 {clause} 对应章节（如涉及职责/流程变化）")
    if doc_ref:
        docs.append(doc_ref)

    horizontal = []
    if cl:
        horizontal = [f"排查同类过程/产线是否存在相同问题（依据 {clause} 常见不符合：{cl.common_nc[0] if cl.common_nc else '同类偏差'}）"]

    owner = _owner_hint(clause, severity)
    return CapaPlan(correction=correction, corrective_actions=corrective[:4],
                    verification=verification[:3], owner_suggestion=owner,
                    timeline={"纠正": fast, "纠正措施": slow},
                    horizontal_check=horizontal, documents_to_update=docs, source=source)


def _owner_hint(clause: str, severity: str) -> str:
    if clause.startswith("7.1.5"):
        return "品质部/计量管理员"
    if clause.startswith("7.5"):
        return "体系管理部/文件管理员"
    if clause.startswith("8.4"):
        return "采购部/供方管理员"
    if clause.startswith("8.5") or clause.startswith("8.6") or clause.startswith("8.7"):
        return "生产部/品质部"
    if clause.startswith("9."):
        return "体系管理部/管理者代表"
    if clause.startswith("10."):
        return "责任部门/品质部"
    if clause.startswith("6.") or clause.startswith("4."):
        return "管理者代表/体系管理部"
    return "责任部门负责人"
