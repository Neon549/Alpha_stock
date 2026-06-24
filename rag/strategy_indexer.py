#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@author: yulin
@description: 策略文档RAG索引 —— ChromaDB版本
原来用FAISS，现在迁移到ChromaDB
改动点：
  1. 去掉FAISS的save_local/load_local，ChromaDB自动持久化
  2. 去掉手动embedding传入，ChromaDB内置embedding函数
  3. retrieve_strategy_knowledge接口完全不变，trading_graph.py无需改动
"""

import threading
from chromadb.utils import embedding_functions
import chromadb
from rag.strategy_docs import STRATEGY_DOCUMENTS
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ChromaDB持久化路径（替代原来的 rag/faiss_index/strategy_knowledge）
CHROMA_DB_PATH = "./chroma_db"
COLLECTION_NAME = "strategy_knowledge"

# 线程锁，保留原来的线程安全设计
_client = None
_collection = None
_lock = threading.Lock()


def _get_collection():
    """
    单例模式获取ChromaDB collection
    保留原来的线程安全单例设计
    """
    global _client, _collection
    if _collection is None:
        with _lock:
            if _collection is None:
                # 持久化客户端，数据自动存到./chroma_db，不用手动save
                _client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

                # 用和原来一样的中文embedding模型
                embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="shibing624/text2vec-base-chinese"
                )

                _collection = _client.get_or_create_collection(
                    name=COLLECTION_NAME,
                    embedding_function=embedding_fn,
                    metadata={"hnsw:space": "cosine"},  # 余弦相似度，和FAISS一致
                )

                # 如果collection是空的，自动build索引
                if _collection.count() == 0:
                    _build_index(_collection)

    return _collection


def _build_index(collection):
    """
    构建策略知识库索引
    对应原来的 build_strategy_index()
    """
    print("🔨 构建策略知识库索引（ChromaDB）...")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=50,
        separators=["\n", "。", "，", " "],
    )

    documents = []
    metadatas = []
    ids = []

    idx = 0
    for doc in STRATEGY_DOCUMENTS:
        full_text = f"{doc['title']}\n{doc['content']}"
        chunks = splitter.split_text(full_text)

        for chunk in chunks:
            documents.append(chunk)
            metadatas.append({"title": doc["title"]})
            ids.append(f"strategy_{idx}")
            idx += 1

    print(f"📄 切块完成：{len(STRATEGY_DOCUMENTS)}篇文档 → {len(documents)}个块")

    # ChromaDB自动embedding，不需要手动调embedding模型
    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids,
    )

    print(f"💾 策略索引已存入ChromaDB：{CHROMA_DB_PATH}/{COLLECTION_NAME}")


def retrieve_strategy_knowledge(query: str, k: int = 2) -> str:
    """
    检索与query最相关的策略知识
    供 backtest_interpreter_node 调用

    接口和原来完全一样，trading_graph.py无需改动
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
        for doc_text, meta in zip(results["documents"][0], results["metadatas"][0]):
            title = meta.get("title", "")
            output.append(f"【{title}】\n{doc_text}")

        return "\n\n".join(output)

    except Exception as e:
        print(f"[StrategyRAG] 检索失败: {e}")
        return ""


# ── 以下是原来有但现在不再需要的函数，保留空壳兼容旧代码 ────────────


def build_strategy_index():
    """
    兼容旧接口，ChromaDB版本在首次get_collection时自动build
    """
    collection = _get_collection()
    print(f"✅ 策略索引已就绪，当前共 {collection.count()} 个文档块")
    return collection


def load_strategy_index():
    """
    兼容旧接口，ChromaDB版本不需要手动load
    """
    return _get_collection()


def get_or_build_strategy_index():
    """
    兼容旧接口
    """
    return _get_collection()
