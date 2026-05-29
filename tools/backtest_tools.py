#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@author: yulin
@created: 2026/5/29 21:35
@updated: 2026/5/29 21:35
@version: 1.0
@description: 
"""
import os
from langchain_core.tools import tool
from backtest.data_loader import get_stock_data_tushare, get_mock_data
from backtest.engine import run_backtest, format_result
from backtest.strategies import STRATEGY_MAP


def _error(reason: str) -> str:
    return (
        f"[TOOL_ERROR]\n"
        f"tool=run_strategy_backtest\n"
        f"reason={reason}\n"
        f"结论：回测失败，无法生成策略评估报告。"
    )


def _ok(body: str) -> str:
    return f"[TOOL_OK]\ntool=run_strategy_backtest\n{body}"


@tool
def run_strategy_backtest(
    stock_code: str,
    strategy: str = "kdj_macd",
    start_date: str = "20220101",
    end_date: str = "20261231",
    initial_cash: float = 100000.0,
) -> str:
    """
    对指定A股股票执行量化策略回测，返回绩效指标报告。

    参数:
        stock_code:   股票代码，如 '600487' 或 '000001'
        strategy:     策略名: kdj_macd / rsi / boll
        start_date:   回测起始日期 YYYYMMDD，如 '20220101'
        end_date:     回测结束日期 YYYYMMDD，如 '20241231'
        initial_cash: 初始资金(元)，默认100000
    """
    if strategy not in STRATEGY_MAP:
        return _error(f"未知策略'{strategy}'，可选: {list(STRATEGY_MAP.keys())}")

    try:
        token = os.getenv("TUSHARE_TOKEN", "")
        if token:
            df = get_stock_data_tushare(stock_code, start_date, end_date, token)
        else:
            print("[BacktestTool] 无Tushare token，使用模拟数据")
            df = get_mock_data(stock_code, days=500)
    except Exception as e:
        return _error(f"数据获取失败: {e}")

    if df.empty or len(df) < 60:
        return _error(f"数据不足(仅{len(df)}根K线)，回测至少需要60根")

    try:
        result = run_backtest(
            df=df,
            strategy_name=strategy,
            initial_cash=initial_cash,
        )
    except Exception as e:
        return _error(f"回测引擎异常: {e}")

    report_text = format_result(result)
    return _ok(report_text)


@tool
def list_available_strategies() -> str:
    """列出所有可用的回测策略及说明。"""
    return """可用回测策略：
  - kdj_macd: KDJ金叉 + MACD确认策略（双重信号过滤，适合趋势行情）
  - rsi:      RSI超卖买入 / 超买卖出策略（适合震荡行情）
  - boll:     布林带下轨买入 / 上轨卖出策略（适合区间震荡）"""


BACKTEST_TOOLS = [
    run_strategy_backtest,
    list_available_strategies,
]