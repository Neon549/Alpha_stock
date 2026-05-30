#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@author: yulin
@created: 2026/5/29 23:02
@updated: 2026/5/29 23:02
@version: 1.0
@description:
"""

# backtest/optimizer.py
# 参数优化器 —— ReAct循环自动搜索最优参数
#
# 面试讲解：
#   ReAct = Reasoning + Acting
#   每轮：LLM分析当前结果(Reasoning) → 决定下一组参数(Acting) → 执行回测 → 循环
#   与暴力网格搜索的区别：LLM引导搜索方向，不是穷举所有组合

from backtest.engine import run_backtest
from backtest.strategies import STRATEGY_MAP
import backtrader as bt
import backtrader.indicators as btind
import pandas as pd

# ── 可调参数空间定义 ─────────────────────────────
PARAM_SPACE = {
    "rsi": {
        "rsi_period": [6, 9, 14, 21],
        "rsi_low": [20, 25, 30],
        "rsi_high": [70, 75, 80],
    },
    "kdj_macd": {
        "kdj_period": [5, 7, 9],
        "macd_fast": [10, 12],
        "macd_slow": [24, 26],
    },
    "boll": {
        "boll_period": [15, 20, 25],
        "boll_dev": [1.5, 2.0, 2.5],
    },
    "kdj_oversold": {
        "k_threshold": [15, 20, 25, 30],
        "d_threshold": [15, 20, 25, 30],
        "j_threshold": [0, 5, 10, 15],
    },
}


def grid_search(
    df: pd.DataFrame,
    strategy_name: str,
    initial_cash: float = 100_000.0,
    top_n: int = 3,
) -> list[dict]:
    """
    网格搜索最优参数组合。
    返回按夏普比率排序的top_n个结果。
    """
    if strategy_name not in PARAM_SPACE:
        return []

    space = PARAM_SPACE[strategy_name]
    strategy_cls = STRATEGY_MAP[strategy_name]

    # 生成所有参数组合
    import itertools

    keys = list(space.keys())
    values = list(space.values())
    combinations = list(itertools.product(*values))

    print(f"[Optimizer] 策略={strategy_name}, 参数组合数={len(combinations)}")

    results = []
    for combo in combinations:
        params = dict(zip(keys, combo))
        try:
            # 动态创建带参数的策略
            cerebro = bt.Cerebro()
            cerebro.broker.setcash(initial_cash)
            cerebro.broker.setcommission(commission=0.001)

            data_feed = bt.feeds.PandasData(
                dataname=df,
                datetime=None,
                open="open",
                high="high",
                low="low",
                close="close",
                volume="volume",
                openinterest=-1,
            )
            cerebro.adddata(data_feed)
            cerebro.addsizer(bt.sizers.PercentSizer, percents=95)
            cerebro.addstrategy(strategy_cls, **params, printlog=False)

            cerebro.addanalyzer(
                bt.analyzers.SharpeRatio,
                _name="sharpe",
                riskfreerate=0.03,
                annualize=True,
            )
            cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

            start_val = cerebro.broker.getvalue()
            res = cerebro.run()
            end_val = cerebro.broker.getvalue()
            strat = res[0]

            sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio")
            max_dd = (
                strat.analyzers.drawdown.get_analysis()
                .get("max", {})
                .get("drawdown", 0)
            )
            total_trades = (
                strat.analyzers.trades.get_analysis().get("total", {}).get("total", 0)
            )
            won = strat.analyzers.trades.get_analysis().get("won", {}).get("total", 0)
            total_return = (end_val - start_val) / start_val * 100

            results.append(
                {
                    "params": params,
                    "total_return": round(total_return, 2),
                    "sharpe": round(sharpe, 3) if sharpe else None,
                    "max_drawdown": round(max_dd, 2),
                    "trade_count": total_trades,
                    "win_rate": (
                        round(won / total_trades * 100, 1) if total_trades > 0 else 0
                    ),
                }
            )
        except Exception as e:
            continue

    # 按夏普比率排序
    results = [r for r in results if r["sharpe"] is not None]
    results.sort(key=lambda x: x["sharpe"], reverse=True)
    return results[:top_n]


def format_optimization_result(results: list[dict], strategy_name: str) -> str:
    """格式化优化结果为可读文本"""
    if not results:
        return "参数优化未找到有效结果。"

    lines = [f"## 参数优化结果 - {strategy_name.upper()}策略", ""]
    for i, r in enumerate(results, 1):
        lines.append(f"### Top {i}")
        lines.append(f"参数: {r['params']}")
        lines.append(f"总收益: {r['total_return']:+.2f}%")
        lines.append(f"夏普: {r['sharpe']}")
        lines.append(f"最大回撤: -{r['max_drawdown']:.2f}%")
        lines.append(f"交易次数: {r['trade_count']}")
        lines.append(f"胜率: {r['win_rate']}%")
        lines.append("")
    return "\n".join(lines)
