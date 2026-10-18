"""现象定性编排：匹配 -> 分级 -> 陈述 -> 整改 -> 校验。

输出结构与 50-plugin-data-model.md §4.1（POST /analyze）一致。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from . import capa, lexicon, severity
from .matcher import Candidate, MatchResult, explain_exclusion, match
from .store import Store

VAGUE_WORDS = ["加强培训", "提高意识", "完善制度", "严格执行", "加大力度", "有待提高", "管理混乱", "责任心不强"]


def _quote_of(requirement_text: str, limit: int = 80) -> str:
    """从条款原文中截取一段可引用的完整要求（保证是原文子串）。"""
    t = re.sub(r"\s+", " ", requirement_text or "").strip()
    if not t:
        return ""
    idx = t.find("应")
    seg = t[idx:] if idx >= 0 else t
    seg = re.split(r"\s*注\d?[：:]", seg)[0].strip()
    if len(seg) <= limit:
        return seg
    window = seg[:limit]
    cut = max(window.rfind("；"), window.rfind("。"), window.rfind("，"))
    return window[: cut + 1] if cut >= 10 else window


def _evidence_gap(text: str, store: Store, clause: str) -> List[str]:
    cl = store.clause(clause)
    if not cl:
        return []
    gaps = [e for e in cl.evidence if e and e not in text]
    return gaps[:4]


def _next_questions(text: str, store: Store, clause: str) -> List[str]:
    best, score = None, 0.0
    from .tokenizer import cosine, terms
    q = terms(text)
    for c in store.cases_of(clause):
        s = cosine(q, c.doc_terms, store.idf)
        if s > score:
            best, score = c, s
    if best and best.question_chain:
        return best.question_chain[:4]
    cl = store.clause(clause)
    if not cl:
        return []
    return [f"该条款要求的记录（{ '、'.join(cl.evidence[:2]) }）是否齐全、可追溯？",
            f"若已建立规定，现场执行与文件是否一致？（{cl.title}）"]


def _impact(text: str, sev: severity.Severity, clause: str) -> str:
    if sev.level == "MAJOR":
        base = "该情况构成体系性/区域性失效，可能导致不合格输出未被识别或流出，影响体系保证产品和服务合格的能力"
    elif sev.level == "MINOR":
        base = "该情况属个别偏差，可能削弱该过程的控制有效性，但尚未构成体系性失效"
    else:
        base = "该情况存在风险趋势，暂未构成对要求的违反"
    if sev.veto:
        base += f"（关键风险：{sev.veto}）"
    return base


def build_statement(text: str, cand: Candidate, store: Store, sev: severity.Severity,
                    doc_ref: str = "") -> Dict[str, str]:
    cl = store.clause(cand.clause)
    quote = _quote_of(cl.requirement_text, 80) if cl else ""
    basis = f'不符合 GB/T 19001-2016 第 {cand.clause} 条"{quote}"的规定'
    if doc_ref:
        basis += f"；同时不符合 {doc_ref}"
    clean_text = re.sub(r"\s+", " ", text).strip()
    title = cl.title if cl else ""
    return {
        "fact": clean_text,
        "basis": basis,
        "gap": "要求：" + title + "应满足上述规定；实际：" + clean_text[:120],
        "impact": _impact(text, sev, cand.clause),
    }


def analyze(text: str, store: Store, doc_ref: str = "", top_k: int = 3,
            history_hits: int = 0) -> dict:
    res: MatchResult = match(text, store, _opts(top_k))
    if not res.candidates:
        return {"need_human": True, "reason": "无法匹配到任何条款，请补充现象细节",
                "findings": [], "candidates": []}

    main = res.candidates[0]
    sev = severity.assess(text, main.clause, history_hits=history_hits)
    statement = build_statement(text, main, store, sev, doc_ref)
    plan = capa.suggest(main.clause, sev.level, text, store, doc_ref)

    cl = store.clause(main.clause)
    conflicts = []
    for other in res.candidates[1:3]:
        conflicts.append({"clause": other.clause, "title": other.title,
                          "reason": explain_exclusion(main, other, store)})

    findings = {
        "clause_main": {"id": cl.id if cl else main.clause, "number": main.clause,
                        "title": main.title, "confidence": main.confidence},
        "clause_candidates": [
            {"clause": c.clause, "title": c.title, "score": round(c.score, 4),
             "confidence": c.confidence, "matched_terms": c.matched[:6],
             "reasons": c.reasons}
            for c in res.candidates
        ],
        "exclusions": conflicts,
        "severity": sev.to_dict(),
        "statement": statement,
        "capa": plan.to_dict(),
        "matched_cases": [c.id for c in store.cases_of(main.clause)][:3],
        "evidence_gap": _evidence_gap(text, store, main.clause),
        "next_questions": _next_questions(text, store, main.clause),
        "citations": ([{"type": "clause", "id": cl.id, "quote": _quote_of(cl.requirement_text, 80)}]
                      if cl else []),
        "route_note": res.route_note,
        "conflict": main.conflict,
    }
    payload = {"need_human": res.need_human or bool(main.conflict), "findings": [findings]}
    payload["validation"] = validate(payload, store)
    return payload


def _opts(top_k: int):
    from . import config
    return config.MatchOptions(top_k=top_k)


# ------------------------------------------------------------------ 输出校验
def validate(payload: dict, store: Store) -> dict:
    """对应 51 §8：条款存在性、旧版编号、空泛词、引文来源。"""
    issues = []
    f = (payload.get("findings") or [{}])[0]
    clause = (f.get("clause_main") or {}).get("number", "")
    if clause and clause not in store.by_number:
        issues.append(f"条款 {clause} 不在知识库中")
    for cand in f.get("clause_candidates", []):
        num = cand.get("clause", "")
        if num in lexicon.LEGACY_CLAUSES:
            issues.append(f"出现 2008 版条款号 {num}，应改为 {lexicon.LEGACY_CLAUSES[num]}")
    text_blob = " ".join(str(v) for v in (f.get("statement") or {}).values())
    text_blob += " ".join((f.get("capa") or {}).get("corrective_actions", []))
    for w in VAGUE_WORDS:
        if w in text_blob:
            issues.append(f"表述含空泛词：{w}")
    quote = (f.get("citations") or [{}])[0].get("quote", "") if f.get("citations") else ""
    if quote:
        cl = store.clause(clause)
        norm = lambda s: re.sub(r"\s+", "", s or "")
        if cl and norm(quote.rstrip("。；")) not in norm(cl.requirement_text):
            issues.append("引文与标准原文不一致")
    return {"ok": not issues, "issues": issues}
