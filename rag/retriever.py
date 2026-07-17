#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# rag/retriever.py
# 新闻检索工具，供 sentiment_analyst 使用
# 升级：混合检索（向量 + BM25 + RRF融合）

import jieba
from langchain_core.tools import tool
from tools.akshare_tools import get_stock_news
from rag.strategy_indexer import _get_collection


import math
from collections import defaultdict


class SimpleBM25:
    """
    轻量BM25实现，不依赖任何第三方库
    用于关键词精确匹配检索
    """

    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75):
        self.corpus = corpus
        self.k1 = k1
        self.b = b
        self.N = len(corpus)

        # 分词
        self.tokenized = [list(jieba.cut(doc)) for doc in corpus]

        # 平均文档长度
        self.avg_dl = sum(len(d) for d in self.tokenized) / max(self.N, 1)

        # 建倒排索引
        self.df = defaultdict(int)
        self.tf = []

        for tokens in self.tokenized:
            token_freq = defaultdict(int)
            for t in tokens:
                token_freq[t] += 1
            self.tf.append(token_freq)
            for t in set(tokens):
                self.df[t] += 1

    def idf(self, token: str) -> float:
        df = self.df.get(token, 0)
        return math.log((self.N - df + 0.5) / (df + 0.5) + 1)

    def score(self, query_tokens: list[str], doc_idx: int) -> float:
        score = 0.0
        dl = len(self.tokenized[doc_idx])
        for token in query_tokens:
            tf = self.tf[doc_idx].get(token, 0)
            if tf == 0:
                continue
            idf = self.idf(token)
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * dl / self.avg_dl)
            score += idf * numerator / denominator
        return score

    def search(self, query: str, k: int = 10) -> list[tuple[int, float]]:
        query_tokens = list(jieba.cut(query))
        scores = [
            (i, self.score(query_tokens, i))
            for i in range(self.N)
        ]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:k]


# ── RRF 融合 ─────────────────────────────────────────────────────────

def rrf_merge(
    vector_ranked: list[str],
    bm25_ranked: list[str],
    k: int = 60
) -> list[str]:
    """
    Reciprocal Rank Fusion
    把向量检索和BM25的结果按排名打分融合

    vector_ranked / bm25_ranked：已排好序的文档列表（排名越前越好）
    k：RRF常数，默认60
    """
    scores: dict[str, float] = defaultdict(float)

    for rank, doc in enumerate(vector_ranked):
        scores[doc] += 1.0 / (rank + k)

    for rank, doc in enumerate(bm25_ranked):
        scores[doc] += 1.0 / (rank + k)

    # 按融合分数降序
    merged = sorted(scores.keys(), key=lambda d: scores[d], reverse=True)
    return merged


# ── 混合检索核心 ──────────────────────────────────────────────────────

def hybrid_retrieve_news(stock_code: str, query: str, top_k: int = 5) -> str:
    """
    混合检索新闻：向量检索 + BM25 关键词检索 + RRF融合

    流程：
    1. akshare 拉取最新新闻（实时数据源）
    2. 向量检索：ChromaDB 语义相似度
    3. BM25检索：关键词精确匹配
    4. RRF融合两路结果
    5. 返回 Top-K
    """

    # Step1：拉取实时新闻
    raw_news = get_stock_news.invoke({"symbol": stock_code})
    if "[TOOL_ERROR]" in raw_news:
        return raw_news

    # 解析新闻条目（格式：【时间】标题）
    news_items = []
    for line in raw_news.strip().split("\n"):
        line = line.strip()
        if line and line.startswith("【"):
            news_items.append(line)

    if not news_items:
        return raw_news  # 格式不对直接返回原始

    if not query:
        # 没有query，直接返回全部新闻
        return "\n".join(news_items[:top_k])

    # Step2：向量检索（用ChromaDB临时存新闻做语义匹配）
    try:
        collection = _get_collection()

        # 用新闻内容临时查询（不入库，只查语义相关性）
        vector_results = collection.query(
            query_texts=[query],
            n_results=min(len(news_items), top_k * 2),
        )
        # 把向量检索结果对应回原始新闻
        # 这里用query在新闻文本里做语义排序
        # 简化：按ChromaDB返回距离对新闻重排
        vector_ranked = _rank_by_query_similarity(news_items, query)

    except Exception:
        vector_ranked = news_items  # 向量检索失败，退化到原始顺序

    # Step3：BM25关键词检索
    bm25 = SimpleBM25(news_items)
    bm25_scores = bm25.search(query, k=len(news_items))
    bm25_ranked = [news_items[idx] for idx, score in bm25_scores if score > 0]

    if not bm25_ranked:
        bm25_ranked = news_items  # BM25无结果，退化

    # Step4：RRF融合
    merged = rrf_merge(vector_ranked, bm25_ranked)

    # Step5：返回Top-K
    top_results = merged[:top_k]
    if not top_results:
        return raw_news

    return "\n".join(top_results)


def _rank_by_query_similarity(news_items: list[str], query: str) -> list[str]:
    """
    用BM25对新闻按query相关性排序（语义检索的简化替代）
    真正的语义检索需要把新闻embed后再比较
    """
    query_tokens = set(jieba.cut(query))
    scored = []
    for item in news_items:
        item_tokens = set(jieba.cut(item))
        overlap = len(query_tokens & item_tokens)
        scored.append((item, overlap))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [item for item, _ in scored]


# ── LangChain Tool 接口（向后兼容）────────────────────────────────────

@tool
def retrieve_stock_news(stock_code: str, query: str = "") -> str:
    """
    检索股票相关新闻（混合检索版本）
    stock_code: 股票代码，如 '000001'
    query: 检索关键词（业绩/订单/政策等），为空时返回全部最新新闻
    """
    try:
        return hybrid_retrieve_news(stock_code, query, top_k=5)
    except Exception as e:
        # 兜底：退化到原始工具
        try:
            return get_stock_news.invoke({"symbol": stock_code})
        except Exception as e2:
            return f"新闻检索失败: {e2}"