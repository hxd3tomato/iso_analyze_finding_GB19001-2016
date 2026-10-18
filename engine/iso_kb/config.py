"""全局配置：路径、权重、阈值。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# 知识库根目录（可通过环境变量覆盖）
KB_DIR = os.environ.get(
    "ISO_KB_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "knowledge")),
)
DATA_DIR = os.path.join(KB_DIR, "data")
DB_PATH = os.environ.get(
    "ISO_KB_DB",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "build", "iso_kb.sqlite3")),
)

# 融合权重（与 00-index §8 对齐）
W_DENSE = 0.45      # 语义相似（此处为加权词项余弦）
W_EVIDENCE = 0.25   # 证据命中率
W_PRIOR = 0.20      # 结构先验（条款触发词）
W_CASE = 0.10       # 历史案例相似度

# 置信度分档
CONF_DIRECT = 0.80
CONF_CANDIDATE = 0.60
CONF_FLOOR = 0.40

# 规则开关
RULE_SPECIFICITY_MARGIN = 0.10   # RULE-01：父子条款分差在此以内时取子条款
RULE_EXCLUSION_GAP = 0.08        # 候选间分差小于此值则标注"需人工确认"

# 严重程度阈值（30-nc-taxonomy §2.2）
SEV_MAJOR = 70
SEV_MINOR = 40


@dataclass
class MatchOptions:
    top_k: int = 3
    explain: bool = True
    allow_parent: bool = True          # 是否允许返回父条款
    boost: dict = field(default_factory=dict)   # 人工指定的条款加权 {clause: delta}


@dataclass
class Weights:
    dense: float = W_DENSE
    evidence: float = W_EVIDENCE
    prior: float = W_PRIOR
    case: float = W_CASE
