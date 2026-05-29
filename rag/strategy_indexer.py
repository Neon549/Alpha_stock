#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@author: yulin
@created: 2026/5/29 22:57
@updated: 2026/5/29 22:57
@version: 1.0
@description: 
"""
# rag/strategy_indexer.py
# 策略文档RAG索引构建器
# 与现有 rag/indexer.py 分开，避免干扰股票新闻索引

import os
import threading
from pathlib import Path
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from rag.strategy_docs import STRATEGY_DOCUMENTS

STRATEGY_INDEX_PATH = "rag/faiss_index/strategy_knowledge"

_embeddings = None
_embeddings_lock = threading.Lock()


def get_embeddings():
    global _embeddings
    if _embeddings is None:
        with _embeddings_lock:
            if _embeddings is None:
                _embeddings = HuggingFaceEmbeddings(
                    model_name="shibing624/text2vec-base-chinese",
                    model_kwargs={"device": "cpu"},
                    encode_kwargs={"normalize_embeddings": True},
                )
    return _embeddings


def build_strategy_index() -> FAISS:
    """构建策略知识库FAISS索引"""
    print("🔨 构建策略知识库索引...")

    texts = []
    metadatas = []
    for doc in STRATEGY_DOCUMENTS:
        texts.append(f"{doc['title']}\n{doc['content']}")
        metadatas.append({"title": doc["title"]})

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=50,
        separators=["\n", "。", "，", " "],
    )

    split_texts = []
    split_metas = []
    for text, meta in zip(texts, metadatas):
        chunks = splitter.split_text(text)
        split_texts.extend(chunks)
        split_metas.extend([meta] * len(chunks))

    print(f"📄 切块完成：{len(STRATEGY_DOCUMENTS)}篇文档 → {len(split_texts)}个块")

    embeddings = get_embeddings()
    vectorstore = FAISS.from_texts(
        texts=split_texts,
        embedding=embeddings,
        metadatas=split_metas,
    )

    os.makedirs(STRATEGY_INDEX_PATH, exist_ok=True)
    vectorstore.save_local(STRATEGY_INDEX_PATH)
    print(f"💾 策略索引已保存: {STRATEGY_INDEX_PATH}")
    return vectorstore


def load_strategy_index() -> FAISS | None:
    if not Path(STRATEGY_INDEX_PATH).exists():
        return None
    embeddings = get_embeddings()
    return FAISS.load_local(
        STRATEGY_INDEX_PATH,
        embeddings,
        allow_dangerous_deserialization=True,
    )


def get_or_build_strategy_index() -> FAISS:
    vs = load_strategy_index()
    if vs is None:
        vs = build_strategy_index()
    return vs


def retrieve_strategy_knowledge(query: str, k: int = 2) -> str:
    """
    检索与query最相关的策略知识
    供 backtest_interpreter_node 调用
    """
    try:
        vs = get_or_build_strategy_index()
        docs = vs.similarity_search(query, k=k)
        if not docs:
            return ""
        results = []
        for doc in docs:
            results.append(
                f"【{doc.metadata.get('title', '')}】\n{doc.page_content}"
            )
        return "\n\n".join(results)
    except Exception as e:
        print(f"[StrategyRAG] 检索失败: {e}")
        return ""