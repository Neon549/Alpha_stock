#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@author: yulin
@created: 2026/5/30 11:43
@updated: 2026/5/30 11:43
@version: 1.0
@description:
"""

# backtest/fundamental_filter.py
# 基本面因子筛选器
# 从候选股票池中筛选出基本面优质的股票

import akshare as ak
import pandas as pd
from pathlib import Path
import json
import os
from datetime import datetime

CACHE_DIR = Path(__file__).parent / "fundamental_cache"
CACHE_DIR.mkdir(exist_ok=True)


def get_fundamental_data(stock_code: str, force_refresh: bool = False) -> dict:
    cache_file = CACHE_DIR / f"{stock_code}_fundamental.json"

    if cache_file.exists() and not force_refresh:
        mtime = cache_file.stat().st_mtime
        age_days = (datetime.now().timestamp() - mtime) / 86400
        if age_days < 30:
            with open(cache_file) as f:
                return json.load(f)

    print(f"[FundamentalFilter] 拉取 {stock_code} 财务数据...")

    result = {
        "stock_code": stock_code,
        "pe": None,
        "pb": None,
        "roe": None,
        "revenue_growth": None,
        "gross_margin": None,
        "updated_at": datetime.now().isoformat(),
    }

    try:
        import yfinance as yf

        suffix = ".SS" if stock_code.startswith("6") else ".SZ"
        ticker = yf.Ticker(f"{stock_code}{suffix}")
        info = ticker.info or {}

        result["pe"] = info.get("trailingPE")
        result["pb"] = info.get("priceToBook")
        result["roe"] = round(float(info.get("returnOnEquity") or 0) * 100, 2)
        result["gross_margin"] = round(float(info.get("grossMargins") or 0) * 100, 2)
        result["revenue_growth"] = round(float(info.get("revenueGrowth") or 0) * 100, 2)
        # get_fundamental_data里加
        result["price"] = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
            or 0
        )
        result["market_cap"] = info.get("marketCap")
    except Exception as e:
        print(f"[FundamentalFilter] 数据获取失败: {e}")

    with open(cache_file, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def score_stock(data: dict) -> float:
    """
    给股票基本面打分（0-100）
    科技股评分体系
    """
    score = 50.0  # 基础分

    # PE评分（科技股PE 20-60合理）
    pe = data.get("pe", 0) or 0
    if 0 < pe <= 30:
        score += 20
    elif 30 < pe <= 60:
        score += 10
    elif pe > 100:
        score -= 20

    # PB评分
    pb = data.get("pb", 0) or 0
    if 0 < pb <= 3:
        score += 10
    elif 3 < pb <= 8:
        score += 5
    elif pb > 15:
        score -= 10

    # ROE评分（>15%为优质）
    roe = data.get("roe", 0) or 0
    if roe >= 20:
        score += 20
    elif roe >= 15:
        score += 15
    elif roe >= 10:
        score += 5
    elif roe < 5:
        score -= 10

    # 毛利率评分（科技股>30%为好）
    gm = data.get("gross_margin", 0) or 0
    if gm >= 40:
        score += 10
    elif gm >= 30:
        score += 5
    elif gm < 15:
        score -= 10

    return min(max(score, 0), 100)


def filter_stocks(
    stock_dict: dict,
    min_score: float = 60.0,
    top_n: int = 5,
) -> list[dict]:
    """
    对股票池进行基本面筛选。

    参数:
        stock_dict: {code: name} 或 {code: {name, sector}}
        min_score:  最低评分门槛
        top_n:      返回前N只

    返回:
        按评分排序的股票列表
    """
    results = []

    for code, info in stock_dict.items():
        name = info if isinstance(info, str) else info.get("name", code)
        sector = info.get("sector", "") if isinstance(info, dict) else ""

        data = get_fundamental_data(code)
        score = score_stock(data)

        # 市值过滤：100-300亿
        market_cap = data.get("market_cap") or 0
        if not (10_000_000_000 < market_cap < 30_000_000_000):
            print(f"  {name}({code}) 跳过：市值{market_cap/1e8:.0f}亿")
            continue

        results.append(
            {
                "code": code,
                "name": name,
                "sector": sector,
                "score": round(score, 1),
                "pe": data.get("pe"),
                "pb": data.get("pb"),
                "roe": data.get("roe"),
                "gross_margin": data.get("gross_margin"),
            }
        )

        print(
            f"  {name}({code}): 评分={score:.0f} PE={data.get('pe')} ROE={data.get('roe')}%"
        )

    # 过滤+排序
    qualified = [r for r in results if r["score"] >= min_score]
    qualified.sort(key=lambda x: x["score"], reverse=True)
    return qualified[:top_n]


def format_filter_result(results: list[dict]) -> str:
    """格式化筛选结果"""
    if not results:
        return "没有股票通过基本面筛选。"

    lines = ["## 基本面筛选结果", ""]
    for i, r in enumerate(results, 1):
        lines.append(f"### Top {i}: {r['name']}({r['code']}) [{r['sector']}]")
        lines.append(f"综合评分: {r['score']}")
        lines.append(
            f"PE: {r['pe']} | PB: {r['pb']} | ROE: {r['roe']}% | 毛利率: {r['gross_margin']}%"
        )
        lines.append("")
    return "\n".join(lines)
