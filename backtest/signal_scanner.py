#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@author: yulin
@created: 2026/5/31 21:52
@updated: 2026/5/31 21:52
@version: 1.0
@description:
"""

# backtest/signal_scanner.py
# 今日买点扫描器
# 对股票池进行KDJ信号检测，输出今日买点列表

import os
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)


def calc_kdj(df: pd.DataFrame) -> pd.DataFrame:
    """计算KDJ指标"""
    low_min = df["low"].rolling(9).min()
    high_max = df["high"].rolling(9).max()
    rsv = (df["close"] - low_min) / (high_max - low_min + 1e-10) * 100
    df["K"] = rsv.ewm(com=2).mean()
    df["D"] = df["K"].ewm(com=2).mean()
    df["J"] = 3 * df["K"] - 2 * df["D"]
    df["MA20"] = df["close"].rolling(20).mean()
    return df


def check_signal(df: pd.DataFrame) -> dict:
    """
    检测今日是否为买点
    条件：K<25 且 J<15 且 价格>MA20 且 MA20近5天向上
    """
    if len(df) < 30:
        return {"signal": False, "reason": "数据不足"}

    df = calc_kdj(df)
    latest = df.iloc[-1]
    prev_ma = df.iloc[-6]["MA20"]

    k = round(float(latest["K"]), 1)
    j = round(float(latest["J"]), 1)
    close = round(float(latest["close"]), 2)
    ma20 = round(float(latest["MA20"]), 2)
    ma20_rising = float(latest["MA20"]) > float(prev_ma)

    k_ok = k < 25
    j_ok = j < 15
    ma_ok = close > ma20
    rise_ok = ma20_rising

    signal = k_ok and j_ok and ma_ok and rise_ok

    conditions = []
    conditions.append(f"K={k} {'✅' if k_ok else '❌'}")
    conditions.append(f"J={j} {'✅' if j_ok else '❌'}")
    conditions.append(f"价格{close}>MA20({ma20}) {'✅' if ma_ok else '❌'}")
    conditions.append(f"MA20向上 {'✅' if rise_ok else '❌'}")

    return {
        "signal": signal,
        "k": k,
        "j": j,
        "close": close,
        "ma20": ma20,
        "ma20_rising": ma20_rising,
        "conditions": conditions,
    }


def scan_today(
    stock_dict: dict = None,
    base_start: str = None,
    top_n: int = 20,
) -> list[dict]:
    from backtest.stock_universe import ALL_STOCKS
    from backtest.data_loader import get_stock_data_incremental  # 改这里

    token = os.getenv("TUSHARE_TOKEN", "")
    if not token:
        raise ValueError("未配置TUSHARE_TOKEN")

    if stock_dict is None:
        stock_dict = {code: info["name"] for code, info in ALL_STOCKS.items()}

    results = []
    total = len(stock_dict)

    for i, (code, name) in enumerate(stock_dict.items()):
        print(f"[Scanner] {i+1}/{total} 检测 {name}({code})...", end=" ")
        try:
            df = get_stock_data_incremental(
                code, base_start=base_start, token=token
            )  # 改这里
            result = check_signal(df)

            if result["signal"]:
                print(f"🟢 买点! K={result['k']} J={result['j']}")
                results.append(
                    {
                        "code": code,
                        "name": name,
                        "k": result["k"],
                        "j": result["j"],
                        "close": result["close"],
                        "ma20": result["ma20"],
                        "conditions": result["conditions"],
                    }
                )
            else:
                print(f"⏳ 无信号")
        except Exception as e:
            if "频率超限" in str(e):
                print(f"⚠️ 频率超限，等待60秒...")
                import time

                time.sleep(60)
                try:
                    df = get_stock_data_incremental(
                        code, base_start=base_start, token=token
                    )
                    import time

                    time.sleep(1.2)  # 限速50次/分钟
                    result = check_signal(df)
                    if result["signal"]:
                        print(f"🟢 买点! K={result['k']} J={result['j']}")
                        results.append(
                            {
                                "code": code,
                                "name": name,
                                "k": result["k"],
                                "j": result["j"],
                                "close": result["close"],
                                "ma20": result["ma20"],
                                "conditions": result["conditions"],
                            }
                        )
                    else:
                        print(f"⏳ 无信号")
                except Exception as e2:
                    print(f"❌ 重试失败: {e2}")
            else:
                print(f"❌ 失败: {e}")

    results.sort(key=lambda x: x["j"])
    return results[:top_n]


def format_scan_result(results: list[dict]) -> str:
    """格式化扫描结果"""
    if not results:
        return "今日无买点信号"

    lines = [f"## 今日买点扫描结果 — 共{len(results)}只\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"### {i}. {r['name']}({r['code']})")
        lines.append(f"当前价: ¥{r['close']} | MA20: ¥{r['ma20']}")
        lines.append(f"K={r['k']} J={r['j']}")
        for c in r["conditions"]:
            lines.append(f"  {c}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print("开始扫描今日买点...")
    results = scan_today(top_n=10)
    print("\n" + "=" * 50)
    print(format_scan_result(results))
