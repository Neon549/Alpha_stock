#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@author: yulin
@created: 2026/6/1 19:41
@updated: 2026/6/1 19:41
@version: 1.0
@description:
"""

# rag/retriever.py
# 新闻检索工具，供sentiment_analyst使用

from langchain_core.tools import tool
from tools.akshare_tools import get_stock_news


@tool
def retrieve_stock_news(stock_code: str, query: str = "") -> str:
    """
    检索股票相关新闻
    stock_code: 股票代码
    query: 检索关键词（业绩/订单/政策等）
    """
    try:
        result = get_stock_news.invoke({"symbol": stock_code})
        return result
    except Exception as e:
        return f"新闻检索失败: {e}"
