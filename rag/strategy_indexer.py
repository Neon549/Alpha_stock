#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略文档RAG索引 —— ChromaDB版本（真实数据增强）

数据来源：
  1. STRATEGY_DOCUMENTS（手写策略知识，静态）
  2. akshare 实时新闻（动态，按需更新）
  3. akshare 财务指标（动态，每季度更新）

存储：ChromaDB PersistentClient，自动持久化到 ./chroma_db
"""

import threading
import time
from datetime import datetime
from chromadb.utils import embedding_functions
import chromadb
from rag.strategy_docs import STRATEGY_DOCUMENTS
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ChromaDB 持久化路径
CHROMA_DB_PATH = "./chroma_db"
COLLECTION_NAME = "strategy_knowledge"

# 线程锁，保证线程安全
_client = None
_collection = None
_lock = threading.Lock()


def _get_collection():
    """单例模式获取 ChromaDB collection"""
    global _client, _collection
    if _collection is None:
        with _lock:
            if _collection is None:
                _client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

                embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="shibing624/text2vec-base-chinese"
                )

                _collection = _client.get_or_create_collection(
                    name=COLLECTION_NAME,
                    embedding_function=embedding_fn,
                    metadata={"hnsw:space": "cosine"},
                )

                # 空库才建索引
                if _collection.count() == 0:
                    _build_index(_collection)

    return _collection


def _build_index(collection):
    """构建完整索引：静态策略文档 + 真实财务数据"""
    print("🔨 构建策略知识库索引...")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=50,
        separators=["\n", "。", "，", " "],
    )

    documents = []
    metadatas = []
    ids = []
    idx = 0

    # ── Part1：静态策略知识文档 ──────────────────────────────
    print("📚 载入静态策略知识文档...")
    for doc in STRATEGY_DOCUMENTS:
        full_text = f"{doc['title']}\n{doc['content']}"
        chunks = splitter.split_text(full_text)
        for chunk in chunks:
            documents.append(chunk)
            metadatas.append({
                "title": doc["title"],
                "source": "strategy_docs",
                "type": "static",
                "date": "static"
            })
            ids.append(f"static_{idx}")
            idx += 1

    print(f"   ✅ 静态文档：{len(STRATEGY_DOCUMENTS)}篇 → {idx}个块")

    # ── Part2：真实财务指标数据（主要持仓股票）────────────────
    print("📊 载入真实财务指标数据...")
    target_stocks = [
        ("000001", "平安银行"),
        ("600036", "招商银行"),
        ("000858", "五粮液"),
        ("600519", "贵州茅台"),
        ("000002", "万科A"),
    ]

    real_count = 0
    for stock_code, stock_name in target_stocks:
        try:
            from tools.akshare_tools import get_financial_indicator
            result = get_financial_indicator.invoke({"symbol": stock_code})

            if "[TOOL_ERROR]" not in result and result.strip():
                doc_text = f"{stock_name}（{stock_code}）财务指标\n{result}"
                chunks = splitter.split_text(doc_text)
                for chunk in chunks:
                    documents.append(chunk)
                    metadatas.append({
                        "title": f"{stock_name}财务指标",
                        "source": "akshare_financial",
                        "type": "realtime",
                        "stock_code": stock_code,
                        "date": datetime.now().strftime("%Y-%m-%d")
                    })
                    ids.append(f"financial_{stock_code}_{idx}")
                    idx += 1
                real_count += 1
                print(f"   ✅ {stock_name} 财务数据入库")
                time.sleep(0.5)  # 避免限流

        except Exception as e:
            print(f"   ⚠️ {stock_name} 财务数据获取失败: {e}")

    print(f"   真实财务数据：{real_count}/{len(target_stocks)} 只股票入库")

    # ── 统一入库 ─────────────────────────────────────────────
    if documents:
        collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        print(f"💾 索引构建完成：共 {len(documents)} 个文档块 → {CHROMA_DB_PATH}")
    else:
        print("⚠️ 没有文档入库")


def update_realtime_data(stock_code: str):
    """
    增量更新：把某只股票的最新新闻入库
    供定时任务调用，不需要重建整个索引
    """
    collection = _get_collection()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=50,
    )

    try:
        from tools.akshare_tools import get_stock_news
        news_result = get_stock_news.invoke({"symbol": stock_code})

        if "[TOOL_ERROR]" in news_result:
            return

        today = datetime.now().strftime("%Y-%m-%d")
        doc_id = f"news_{stock_code}_{today}"

        # 检查今天的新闻是否已入库
        existing = collection.get(ids=[doc_id])
        if existing["ids"]:
            print(f"[RAG] {stock_code} 今日新闻已存在，跳过")
            return

        # 入库
        chunks = splitter.split_text(news_result)
        for i, chunk in enumerate(chunks):
            collection.add(
                documents=[chunk],
                metadatas=[{
                    "title": f"{stock_code}最新新闻",
                    "source": "akshare_news",
                    "type": "realtime",
                    "stock_code": stock_code,
                    "date": today
                }],
                ids=[f"{doc_id}_{i}"]
            )

        print(f"[RAG] {stock_code} 新闻增量入库完成")

    except Exception as e:
        print(f"[RAG] 增量更新失败: {e}")


def retrieve_strategy_knowledge(query: str, k: int = 3) -> str:
    """
    检索与 query 最相关的策略知识
    供 researcher_node 和 backtest_interpreter_node 调用
    """
    try:
        collection = _get_collection()

        results = collection.query(
            query_texts=[query],
            n_results=k,
        )

        if not results["documents"] or not results["documents"][0]:
            return ""

        output = []
        for doc_text, meta in zip(
            results["documents"][0],
            results["metadatas"][0]
        ):
            title = meta.get("title", "")
            source = meta.get("source", "")
            date = meta.get("date", "")

            # 标注数据来源和时间
            if source == "akshare_financial":
                header = f"【{title}｜真实财务数据｜{date}】"
            elif source == "akshare_news":
                header = f"【{title}｜最新新闻｜{date}】"
            else:
                header = f"【{title}｜策略知识库】"

            output.append(f"{header}\n{doc_text}")

        return "\n\n".join(output)

    except Exception as e:
        print(f"[StrategyRAG] 检索失败: {e}")
        return ""


# ── 兼容旧接口 ────────────────────────────────────────────────────────

def build_strategy_index():
    collection = _get_collection()
    print(f"✅ 策略索引已就绪，当前共 {collection.count()} 个文档块")
    return collection


def load_strategy_index():
    return _get_collection()


def get_or_build_strategy_index():
    return _get_collection()