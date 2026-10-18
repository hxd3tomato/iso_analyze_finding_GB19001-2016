"""中文分词与词项加权。

设计取舍：不引入第三方分词器（离线、零依赖），采用
  1) 领域词典最长匹配（高权重，3.0）
  2) 汉字二元组 bigram（基础权重 1.0）
  3) 数字/编号（权重 0.5，噪音较大）
并用 IDF 抑制高频虚词二元组。在 57 条款的小语料上，该方案与词级 BM25 效果接近。
"""

from __future__ import annotations

import math
import re
from collections import Counter

_CJK = re.compile(r"[\u4e00-\u9fff]+")
_NUM = re.compile(r"[A-Za-z]{0,3}\d+(?:\.\d+)*")
_PUNCT = re.compile(r"[\s，。；：、！？（）()《》【】\[\]\"'“”‘’·,.;:!?\-—_/\\|]+")

# 领域词典：多字术语，命中权重高
DOMAIN_TERMS = [
    # 计量
    "校准", "检定", "量具", "卡尺", "千分尺", "游标卡尺", "计量器具", "溯源", "失准", "超差", "超期未校准",
    # 文件
    "受控", "作废", "版本", "发放", "回收", "受控文件", "文件控制", "作业指导书", "修订", "换版",
    # 审核
    "内审", "内部审核", "内审员", "审核方案", "审核计划", "检查表", "不符合项", "观察项", "管理评审",
    # 不合格与改进
    "不合格品", "让步接收", "特采", "返工", "返修", "报废", "隔离", "纠正措施", "原因分析", "重复发生", "闭环",
    # 生产
    "首件", "巡检", "工艺参数", "特殊过程", "过程确认", "再确认", "淬火", "焊接", "热处理", "灭菌", "防错",
    # 采购
    "供方", "供应商", "合格供方", "再评价", "来料", "进货检验", "外包", "外协",
    # 设计与变更
    "设计开发", "设计评审", "设计验证", "设计确认", "变更", "更改", "工程变更", "ECN", "改图",
    # 顾客
    "顾客满意", "满意度", "投诉", "客诉", "合同评审", "订单评审",
    # 体系
    "质量方针", "质量目标", "风险和机遇", "相关方", "环境因素", "过程清单", "删减", "不适用", "范围",
    # 设施
    "特种设备", "压力容器", "储气罐", "叉车", "起重机械", "点检", "保养", "设备台账",
    # 追溯
    "追溯", "批次", "标识", "状态标识", "唯一性标识",
    # 能力意识
    "培训", "能力", "资格证", "胜任", "意识", "宣贯",
]

_TERM_SET = sorted(set(DOMAIN_TERMS), key=len, reverse=True)


def normalize(text: str) -> str:
    return _PUNCT.sub(" ", text.lower()).strip()


def terms(text: str) -> Counter:
    """返回 {词项: 权重}。"""
    text = normalize(text)
    out: Counter = Counter()

    # 1) 领域词典最长匹配
    for term in _TERM_SET:
        cnt = text.count(term)
        if cnt:
            out[term] += 3.0 * cnt
            text = text.replace(term, " ")

    # 2) 剩余汉字串 -> bigram
    for run in _CJK.findall(text):
        run = run.strip()
        if len(run) == 1:
            out[run] += 1.0
            continue
        for i in range(len(run) - 1):
            out[run[i:i + 2]] += 1.0

    # 3) 编号/数字
    for num in _NUM.findall(text):
        out[num] += 0.5
    return out


def matched_terms(query: str, doc_terms: set) -> list:
    """返回查询中命中文档的高权重词项（用于解释"为何匹配"）。"""
    q = terms(query)
    hits = [(t, w) for t, w in q.items() if t in doc_terms and len(t) >= 2]
    hits.sort(key=lambda x: (-x[1], -len(x[0])))
    return [t for t, _ in hits]


class Idf:
    """基于语料统计的 IDF。"""

    def __init__(self, docs: list):
        self.n = max(1, len(docs))
        df: Counter = Counter()
        for d in docs:
            for t in set(d):
                df[t] += 1
        self.df = df

    def __call__(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log((self.n + 1) / (df + 0.5)) + 1.0


def cosine(q: Counter, d: Counter, idf: Idf) -> float:
    if not q or not d:
        return 0.0
    num = 0.0
    for t, wq in q.items():
        wd = d.get(t)
        if wd:
            num += (wq * idf(t)) * (wd * idf(t))
    qn = math.sqrt(sum((w * idf(t)) ** 2 for t, w in q.items()))
    dn = math.sqrt(sum((w * idf(t)) ** 2 for t, w in d.items()))
    if qn == 0 or dn == 0:
        return 0.0
    return num / (qn * dn)
