"""条款匹配引擎。

流程（对应 51-retrieval-and-prompts.md §1.3）：
  现象 -> 词项加权 -> 稠密(余弦) + 证据命中 + 结构先验 + 案例相似 -> 融合
       -> RULE-01 具体性收敛 -> RULE-02 变更分流 -> 输出候选与排除理由
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import config, lexicon
from .store import Clause, Store
from .tokenizer import cosine, matched_terms, terms


@dataclass
class Candidate:
    clause: str
    title: str
    score: float
    confidence: float
    parts: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    matched: List[str] = field(default_factory=list)
    conflict: str = ""

    def to_dict(self) -> dict:
        return {
            "clause": self.clause,
            "title": self.title,
            "score": round(self.score, 4),
            "confidence": round(self.confidence, 4),
            "parts": {k: round(v, 4) for k, v in self.parts.items()},
            "reasons": self.reasons,
            "matched_terms": self.matched[:8],
            "conflict": self.conflict,
        }


@dataclass
class MatchResult:
    text: str
    candidates: List[Candidate]
    need_human: bool
    route_note: str = ""

    @property
    def main(self) -> Optional[Candidate]:
        return self.candidates[0] if self.candidates else None

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "need_human": self.need_human,
            "route_note": self.route_note,
            "candidates": [c.to_dict() for c in self.candidates],
        }


def _evidence_hit(text: str, clause: Clause) -> float:
    hits = 0
    for ev in clause.evidence_terms:
        if len(ev) >= 2 and ev in text:
            hits += 1
    # 条款"常见不符合"中的短语也作为弱证据
    return min(1.0, hits / 2.0)


def _case_sim(q, clause_number: str, store: Store) -> float:
    best = 0.0
    for c in store.cases_of(clause_number):
        s = cosine(q, c.doc_terms, store.idf)
        if s > best:
            best = s
    return best


def _calibrate(raw: float, margin: float = 1.0) -> float:
    """融合分 -> 置信度。

    经验区间（34 条标注样本）：命中条款 raw 多在 0.17~0.55。
    以 0.15 为中心做 logistic，并用与次优候选的分差做轻微折扣。
    """
    base = 1.0 / (1.0 + math.exp(-6.5 * (raw - 0.15)))
    if margin < 0.05:
        base *= 0.90
    return round(min(0.98, max(0.02, base)), 4)


def match(text: str, store: Store, opts: Optional[config.MatchOptions] = None) -> MatchResult:
    opts = opts or config.MatchOptions()
    q = terms(text)
    prior = lexicon.prior_scores(text)
    route_clause, route_label = lexicon.route_change(text)

    # 变更分流：增强目标条款，压制同族其它条款
    if route_clause:
        prior[route_clause] = max(prior.get(route_clause, 0.0), 0.92)
        for family in ("6.3", "8.2.4", "8.3.6", "8.5.6"):
            if family != route_clause:
                prior[family] = min(prior.get(family, 0.0), 0.15)

    # 文件类分流（RULE-04）：区分"要素不全(7.5.2)"与"控不住(7.5.3)"
    dc_clause, dc_label = lexicon.route_doc_control(text)
    if dc_clause and not route_clause:
        prior[dc_clause] = max(prior.get(dc_clause, 0.0), 0.93)
        for family in ("7.5.1", "7.5.2", "7.5.3"):
            if family != dc_clause:
                prior[family] = min(prior.get(family, 0.0), 0.12)
        route_label = route_label or dc_label

    # 储存/防护分流（8.5.2 vs 8.5.4）
    st_clause, st_label = lexicon.route_storage(text)
    if st_clause and not route_clause:
        prior[st_clause] = max(prior.get(st_clause, 0.0), 0.90)
        prior["8.5.2"] = min(prior.get("8.5.2", 0.0), 0.20)
        route_label = route_label or st_label

    cands: List[Candidate] = []
    for c in store.clauses:
        sim = cosine(q, c.doc_terms, store.idf)
        ev = _evidence_hit(text, c)
        pr = prior.get(c.number, 0.0)
        cs = _case_sim(q, c.number, store)
        raw = (config.W_DENSE * sim + config.W_EVIDENCE * ev
               + config.W_PRIOR * pr + config.W_CASE * cs)
        if raw <= 0.01:
            continue
        cand = Candidate(
            clause=c.number, title=c.title, score=raw, confidence=_calibrate(raw),
            parts={"semantic": sim, "evidence": ev, "prior": pr, "case": cs},
            reasons=lexicon.prior_reasons(text, c.number),
            matched=matched_terms(text, set(c.doc_terms)),
        )
        cands.append(cand)

    cands.sort(key=lambda x: (-x.score, x.clause))
    cands = _apply_specificity(cands, store)
    if cands:
        margin = cands[0].score - (cands[1].score if len(cands) > 1 else 0.0)
        cands[0].confidence = _calibrate(cands[0].score, margin)
    if len(cands) > 1 and (cands[0].score - cands[1].score) < config.RULE_EXCLUSION_GAP:
        cands[0].conflict = "与候选 2 分差不足 0.08，建议人工确认"
    top = cands[: max(1, opts.top_k)]
    need_human = (not top) or top[0].confidence < config.CONF_CANDIDATE
    return MatchResult(text=text, candidates=top, need_human=need_human,
                       route_note=route_label or "")


def _apply_specificity(cands: List[Candidate], store: Store) -> List[Candidate]:
    """RULE-01：父条款与子条款同时候选时，若子条款分差在阈值内则去掉父条款。"""
    drop = set()
    for a in cands:
        for b in cands:
            if a is b:
                continue
            if b.clause.startswith(a.clause + ".") and b.score >= a.score - config.RULE_SPECIFICITY_MARGIN:
                drop.add(a.clause)
                break
    return [c for c in cands if c.clause not in drop]


PAIR_NOTES = {
    ("7.5.3", "7.5.2"): "文件/记录的标识、版本、审批等要素齐全，失效点在分发、回收与访问控制（RULE-04）",
    ("7.5.3", "8.5.1"): "现场文件本身受控，问题在版本控制而非未配备作业文件（RULE-04）",
    ("8.6", "8.7"): "问题发生在放行环节（该检未检/未授权放行），尚未进入不合格品处置（RULE-07）",
    ("8.7", "10.2"): "当前是处置不合格输出，尚未进入原因分析与防止再发生（RULE-11）",
    ("10.2", "8.7"): "已涉及原因分析与纠正措施，超出不合格品处置范围（RULE-11）",
    ("8.2.4", "8.5.6"): "变更源头是顾客要求，属 8.2.4；生产现场 4M1E 变化才是 8.5.6（RULE-02）",
    ("6.3", "5.3"): "职责未更新是结果，根因是体系变更未策划（RULE-02）",
    ("8.5.1", "8.6"): "控制点在过程（参数/首件/人员），不是最终放行（RULE-07）",
}


def explain_exclusion(main: Candidate, other: Candidate, store: Store) -> str:
    note = PAIR_NOTES.get((main.clause, other.clause))
    if note:
        return note
    """生成"为何不是另一条"的理由（用于候选排除说明）。"""
    mc = store.clause(main.clause)
    oc = store.clause(other.clause)
    if not mc or not oc:
        return ""
    main_only = [t for t in other.matched if t not in main.matched]
    if other.parts.get("prior", 0) < main.parts.get("prior", 0) - 0.1:
        return f"未命中 {other.clause} 的特有触发词（如 {oc.title} 相关证据），且缺少该条款要求的记录"
    if other.parts.get("evidence", 0) < 0.5:
        return f"{other.clause} 要求的证据（{ '、'.join(oc.evidence[:2]) }）在现象中未出现"
    if main_only:
        return f"现象指向 {oc.title}，但主条款证据更直接（{ '、'.join(main.matched[:3]) }）"
    return f"按 RULE-01（取最具体条款）与结构先验，{main.clause} 更贴合"
