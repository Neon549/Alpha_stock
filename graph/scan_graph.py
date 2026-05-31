#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@author: yulin
@created: 2026/5/31 21:50
@updated: 2026/5/31 21:50
@version: 1.0
@description:
"""

# graph/scan_graph.py
# 今日扫描图：扫描买点 → 4个Agent分析 → 验证 → 输出

from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from backtest.signal_scanner import scan_today
from agents.fundamental_analyst import run_fundamental_analysis
from agents.technical_analyst import run_technical_analysis
from agents.sentiment_analyst import run_sentiment_analysis
from agents.validator import run_validator


class ScanState(TypedDict):
    candidates: List[dict]  # 扫描出的候选股
    current_index: int  # 当前分析的股票索引
    analysis_results: List[dict]  # 每只股票的分析结果
    final_recommendations: List[dict]  # 最终推荐


def scan_node(state: ScanState) -> ScanState:
    """扫描今日买点"""
    print("🔍 开始扫描今日买点...")
    candidates = scan_today(top_n=5)  # 先取前5只测试
    print(f"✅ 找到{len(candidates)}只候选股")
    return {**state, "candidates": candidates, "current_index": 0}


def analyze_node(state: ScanState) -> ScanState:
    """对候选股跑4个Agent分析"""
    candidates = state["candidates"]
    results = state.get("analysis_results", [])

    for candidate in candidates:
        code = candidate["code"]
        name = candidate["name"]
        print(f"\n📊 分析 {name}({code})...")

        try:
            fundamental = run_fundamental_analysis(code)
            technical = run_technical_analysis(code)
            sentiment = run_sentiment_analysis(code)

            # 验证Agent
            validation = run_validator(
                stock_code=code,
                fundamental_report=fundamental,
                technical_report=technical,
                sentiment_report=sentiment,
                researcher_analysis="",  # 无researcher
            )

            results.append(
                {
                    "code": code,
                    "name": name,
                    "k": candidate["k"],
                    "j": candidate["j"],
                    "close": candidate["close"],
                    "decision": validation["decision"],
                    "confidence": validation["confidence"],
                    "consistent": validation["consistent"],
                    "report": validation["report"],
                }
            )

            print(
                f"→ 决策: {validation['decision']} 置信度: {validation['confidence']}"
            )

        except Exception as e:
            print(f"❌ {name}分析失败: {e}")

    return {**state, "analysis_results": results}


def recommend_node(state: ScanState) -> ScanState:
    """筛选最终推荐"""
    results = state["analysis_results"]

    # 只保留买入且置信度中/高的
    recommendations = [
        r
        for r in results
        if r["decision"] == "买入" and r["confidence"] in ["高", "中"]
    ]

    # 按J值排序（越小越超卖）
    recommendations.sort(key=lambda x: x["j"])

    print(f"\n✅ 最终推荐{len(recommendations)}只股票")
    return {**state, "final_recommendations": recommendations}


def build_scan_graph():
    graph = StateGraph(ScanState)
    graph.add_node("scan", scan_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("recommend", recommend_node)

    graph.set_entry_point("scan")
    graph.add_edge("scan", "analyze")
    graph.add_edge("analyze", "recommend")
    graph.add_edge("recommend", END)

    return graph.compile()


def run_daily_scan() -> dict:
    """运行今日扫描，返回推荐列表"""
    scan_graph = build_scan_graph()
    initial_state = {
        "candidates": [],
        "current_index": 0,
        "analysis_results": [],
        "final_recommendations": [],
    }
    result = scan_graph.invoke(initial_state)
    return result


def build_scan_graph(base_start: str = None):
    # 用闭包传入base_start
    def scan_node(state: ScanState) -> ScanState:
        print("🔍 开始扫描今日买点...")
        candidates = scan_today(top_n=5, base_start=base_start)
        print(f"✅ 找到{len(candidates)}只候选股")
        return {**state, "candidates": candidates, "current_index": 0}

    # 其他node不变...


def run_daily_scan(base_start: str = None) -> dict:
    scan_graph = build_scan_graph(base_start=base_start)
    # 其他不变...
