# -*- coding: utf-8 -*-
"""插件与 Python 引擎之间的 JSON 桥。

用法：python bridge.py <command>   （命令参数从 stdin 读 JSON）

命令：
  health                  健康检查
  analyze  {text, doc_ref?} 
  match    {text, top_k?}
  capa     {clause, severity?, text?, doc_ref?}
  clause   {clause}
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# 强制 UTF-8：Windows 默认 cp936 会把中文参数读成乱码
for stream in (sys.stdin, sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass
sys.path.insert(0, HERE)

DATA_DIR = os.environ.get("ISO_KB_DATA") or os.path.join(HERE, "..", "knowledge", "data")

_store = None


def store():
    global _store
    if _store is None:
        from iso_kb.store import Store
        _store = Store.load(DATA_DIR)
    return _store


def cmd_health(_payload):
    s = store()
    return {"ok": True, "clauses": len(s.clauses), "cases": len(s.cases),
            "items": len(s.items), "data_dir": os.path.abspath(DATA_DIR)}


def cmd_analyze(payload):
    from iso_kb.analyzer import analyze
    text = payload.get("text") or ""
    if not text.strip():
        raise ValueError("text 不能为空")
    return analyze(text, store(), doc_ref=payload.get("doc_ref") or "",
                   top_k=int(payload.get("top_k") or 3))


def cmd_match(payload):
    from iso_kb import config
    from iso_kb.matcher import explain_exclusion, match
    text = payload.get("text") or ""
    if not text.strip():
        raise ValueError("text 不能为空")
    s = store()
    res = match(text, s, config.MatchOptions(top_k=int(payload.get("top_k") or 3)))
    out = res.to_dict()
    for i in range(1, len(res.candidates)):
        out["candidates"][i]["reason_vs_main"] = explain_exclusion(
            res.candidates[0], res.candidates[i], s)
    return out


def cmd_capa(payload):
    from iso_kb import capa, severity
    s = store()
    clause = payload.get("clause") or ""
    if clause not in s.by_number:
        raise ValueError("未知条款 " + clause)
    text = payload.get("text") or ""
    level = payload.get("severity")
    if not level:
        level = severity.assess(text, clause).level if text else "MINOR"
    plan = capa.suggest(clause, level, text, s, payload.get("doc_ref") or "")
    return {"clause": clause, "severity": level, "plan": plan.to_dict()}


def cmd_clause(payload):
    s = store()
    number = (payload.get("clause") or "").strip()
    cl = s.clause(number)
    if not cl:
        raise ValueError("未知条款 " + number)
    cases = [{"id": c.id, "title": c.title, "severity": c.severity,
              "clause_main": c.clause_main} for c in s.cases_of(number)]
    items = [{"id": i.id, "question": i.question, "method": i.method,
              "evidence": i.evidence} for i in s.items_of(number)][:8]
    return {
        "number": cl.number, "title": cl.title, "intent": cl.intent,
        "requirement_text": cl.requirement_text, "evidence": cl.evidence,
        "common_nc": cl.common_nc, "confusable": cl.confusable,
        "confidence": cl.confidence, "cases": cases, "audit_items": items,
    }


COMMANDS = {
    "health": cmd_health,
    "analyze": cmd_analyze,
    "match": cmd_match,
    "capa": cmd_capa,
    "clause": cmd_clause,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(json.dumps({"ok": False, "error": "unknown command"}, ensure_ascii=False))
        return 2
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "bad json: " + str(exc)}, ensure_ascii=False))
        return 2
    try:
        data = COMMANDS[sys.argv[1]](payload)
        print(json.dumps({"ok": True, "data": data}, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001 - 边界处统一转为 JSON 错误
        print(json.dumps({"ok": False, "error": type(exc).__name__ + ": " + str(exc)},
                         ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
