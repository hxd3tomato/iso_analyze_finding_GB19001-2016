"""知识库装载与 SQLite 持久化。

两种使用方式：
  1) Store.load()        —— 直接从 knowledge/data/*.json 载入内存（评测、离线工具）
  2) build_database()    —— 构建 SQLite（含 FTS5），供插件服务长期查询

表结构与 50-plugin-data-model.md §3 一致。
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import config, lexicon
from .tokenizer import Idf, terms


@dataclass
class Clause:
    id: str
    number: str
    title: str
    requirement_text: str
    intent: str
    evidence: List[str]
    common_nc: List[str]
    confusable: str
    confidence: float
    doc_terms: Dict[str, float] = field(default_factory=dict)
    evidence_terms: set = field(default_factory=set)

    @property
    def search_text(self) -> str:
        parts = [self.title, self.intent, self.requirement_text, " ".join(self.common_nc), self.confusable]
        return " ".join(p for p in parts if p)


@dataclass
class Case:
    id: str
    title: str
    phenomenon: str
    clause_main: str
    severity: str
    severity_score: Optional[int]
    basis: str
    question_chain: List[str]
    capa_raw: str
    exclusion: str
    doc_terms: Dict[str, float] = field(default_factory=dict)

    @property
    def search_text(self) -> str:
        return " ".join([self.title, self.phenomenon, self.exclusion])


@dataclass
class AuditItem:
    id: str
    clause: str
    question: str
    method: List[str]
    evidence: List[str]


class Store:
    def __init__(self, clauses: List[Clause], cases: List[Case], items: List[AuditItem]):
        self.clauses = clauses
        self.cases = cases
        self.items = items
        self.by_number = {c.number: c for c in clauses}
        self.idf = Idf([c.doc_terms for c in clauses] + [c.doc_terms for c in cases])
        # 条款级证据词表（用于 evidence_hit）
        self.evidence_vocab = {c.number: c.evidence_terms for c in clauses}

    # ------------------------------------------------------------------ load
    @classmethod
    def load(cls, data_dir: Optional[str] = None) -> "Store":
        data_dir = data_dir or config.DATA_DIR
        clauses_raw = _read_json(os.path.join(data_dir, "clauses.json"))
        cases_raw = _read_json(os.path.join(data_dir, "nc_cases.json"))
        items_raw = _read_json(os.path.join(data_dir, "audit_items.json"))

        clauses: List[Clause] = []
        for r in clauses_raw:
            c = Clause(
                id=r["id"], number=r["number"], title=r["title"],
                requirement_text=r.get("requirement_full") or r.get("requirement_text", ""),
                intent=r.get("intent", ""), evidence=r.get("evidence", []),
                common_nc=r.get("common_nc", []), confusable=r.get("confusable", ""),
                confidence=r.get("confidence", 0.95),
            )
            c.doc_terms = dict(terms(c.search_text))
            c.evidence_terms = _evidence_terms(c)
            clauses.append(c)

        known_numbers = {c.number for c in clauses}
        cases: List[Case] = []
        for r in cases_raw:
            k = Case(
                id=r["id"], title=r["title"], phenomenon=r.get("phenomenon", ""),
                clause_main=lexicon.canonical_clause(r.get("clause_main", ""), known_numbers),
                severity=r.get("severity", ""),
                severity_score=r.get("severity_score"),
                basis=r.get("basis", ""), question_chain=r.get("question_chain", []),
                capa_raw=r.get("capa_raw", ""), exclusion=r.get("exclusion", ""),
            )
            k.doc_terms = dict(terms(k.search_text))
            cases.append(k)

        items: List[AuditItem] = []
        for r in items_raw:
            num = _clause_of_item(r["id"])
            items.append(AuditItem(id=r["id"], clause=num, question=r["question"],
                                   method=r.get("method", []), evidence=r.get("evidence", [])))

        return cls(clauses, cases, items)

    # ------------------------------------------------------------------ query
    def clause(self, number: str) -> Optional[Clause]:
        return self.by_number.get(number)

    def cases_of(self, clause: str) -> List[Case]:
        return [c for c in self.cases if c.clause_main == clause]

    def items_of(self, clause: str) -> List[AuditItem]:
        return [i for i in self.items if i.clause == clause or i.clause.startswith(clause + ".")]

    def parents_of(self, number: str) -> List[str]:
        out, parts = [], number.split(".")
        while len(parts) > 1:
            parts.pop()
            cand = ".".join(parts)
            if cand in self.by_number:
                out.append(cand)
        return out


def _evidence_terms(c: Clause) -> set:
    """从条款的证据清单 + 常见不符合中抽取证据名词。"""
    out = set()
    for e in c.evidence:
        for piece in e.replace("（", " ").replace("）", " ").replace("、", " ").split():
            if len(piece) >= 2:
                out.add(piece)
    for n in c.common_nc:
        for piece in n.replace("，", " ").replace("、", " ").split():
            if 2 <= len(piece) <= 8:
                out.add(piece)
    return out


def _clause_of_item(item_id: str) -> str:
    body = item_id[3:] if item_id.startswith("AI-") else item_id
    body = body.rsplit("-", 1)[0]
    return body.replace("SCOPE", "0")


def _read_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------- SQLite
SCHEMA = """
DROP TABLE IF EXISTS clause;
DROP TABLE IF EXISTS clause_fts;
DROP TABLE IF EXISTS nc_case;
DROP TABLE IF EXISTS nc_case_fts;
DROP TABLE IF EXISTS audit_item;
DROP TABLE IF EXISTS finding;

CREATE TABLE clause (
  id TEXT PRIMARY KEY, number TEXT UNIQUE, title TEXT, chapter INTEGER,
  requirement_text TEXT, intent TEXT, evidence_json TEXT,
  common_nc_json TEXT, confusable TEXT, confidence REAL
);
CREATE VIRTUAL TABLE clause_fts USING fts5(
  number, title, requirement_text, intent, tokenize='unicode61'
);
CREATE TABLE nc_case (
  id TEXT PRIMARY KEY, title TEXT, phenomenon TEXT, clause_main TEXT,
  severity TEXT, severity_score INTEGER, basis TEXT,
  question_chain_json TEXT, capa_raw TEXT, exclusion TEXT
);
CREATE VIRTUAL TABLE nc_case_fts USING fts5(
  title, phenomenon, exclusion, tokenize='unicode61'
);
CREATE TABLE audit_item (
  id TEXT PRIMARY KEY, clause TEXT, question TEXT,
  method_json TEXT, evidence_json TEXT
);
CREATE TABLE finding (
  id TEXT PRIMARY KEY, audit_id TEXT, phenomenon TEXT, clause_main TEXT,
  severity TEXT, severity_score INTEGER, confidence REAL, created_at TEXT
);
"""


def build_database(db_path: Optional[str] = None, data_dir: Optional[str] = None) -> str:
    db_path = db_path or config.DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    store = Store.load(data_dir)

    con = sqlite3.connect(db_path)
    try:
        con.executescript(SCHEMA)
        for c in store.clauses:
            con.execute(
                "INSERT INTO clause VALUES (?,?,?,?,?,?,?,?,?,?)",
                (c.id, c.number, c.title, int(c.number.split(".")[0]),
                 c.requirement_text, c.intent, json.dumps(c.evidence, ensure_ascii=False),
                 json.dumps(c.common_nc, ensure_ascii=False), c.confusable, c.confidence),
            )
            con.execute(
                "INSERT INTO clause_fts VALUES (?,?,?,?)",
                (c.number, c.title, c.requirement_text, c.intent),
            )
        for k in store.cases:
            con.execute(
                "INSERT INTO nc_case VALUES (?,?,?,?,?,?,?,?,?,?)",
                (k.id, k.title, k.phenomenon, k.clause_main, k.severity, k.severity_score,
                 k.basis, json.dumps(k.question_chain, ensure_ascii=False), k.capa_raw, k.exclusion),
            )
            con.execute(
                "INSERT INTO nc_case_fts VALUES (?,?,?)",
                (k.title, k.phenomenon, k.exclusion),
            )
        for i in store.items:
            con.execute(
                "INSERT INTO audit_item VALUES (?,?,?,?,?)",
                (i.id, i.clause, i.question, json.dumps(i.method, ensure_ascii=False),
                 json.dumps(i.evidence, ensure_ascii=False)),
            )
        con.commit()
    finally:
        con.close()
    return db_path
