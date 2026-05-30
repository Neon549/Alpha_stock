#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@author: yulin
@created: 2026/5/29 21:11
@updated: 2026/5/29 21:11
@version: 1.0
@description:
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "data_cache"
CACHE_DIR.mkdir(exist_ok=True)


def _normalize_code(stock_code: str) -> str:
    code = stock_code.strip().split(".")[0]
    if code.startswith("6"):
        return f"{code}.SH"
    else:
        return f"{code}.SZ"


def get_stock_data_tushare(
    stock_code: str,
    start_date: str = "20220101",
    end_date: str = "20261231",
    token: str = "",
) -> pd.DataFrame:
    ts_code = _normalize_code(stock_code)
    token = token or os.getenv("TUSHARE_TOKEN", "")

    if not token:
        raise ValueError("Tushare token未设置。请在.env中添加 TUSHARE_TOKEN=xxx")

    cache_file = CACHE_DIR / f"{ts_code}_{start_date}_{end_date}.csv"

    if cache_file.exists():
        print(f"[DataLoader] 读取缓存: {cache_file.name}")
        df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
        return df

    print(f"[DataLoader] 从Tushare拉取: {ts_code} {start_date}~{end_date}")
    import tushare as ts

    ts.set_token(token)
    pro = ts.pro_api()

    raw = pro.daily(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
        fields="trade_date,open,high,low,close,vol",
    )

    if raw is None or raw.empty:
        raise ValueError(f"Tushare返回空数据: {ts_code}")

    df = raw.rename(columns={"trade_date": "datetime", "vol": "volume"})
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()
    df = df[["open", "high", "low", "close", "volume"]].astype(float)

    df.to_csv(cache_file)
    print(f"[DataLoader] 已缓存: {cache_file.name} ({len(df)}根K线)")
    return df


def get_mock_data(stock_code: str = "000001", days: int = 500) -> pd.DataFrame:
    np.random.seed(hash(stock_code) % 2**32)
    dates = pd.date_range(end=pd.Timestamp.today(), periods=days, freq="B")
    price = 15.0
    prices = []

    trend = 0.0001
    for i in range(days):
        if i % 50 == 0:
            trend = np.random.choice([-0.001, 0.0, 0.001])
        price *= 1 + trend + np.random.normal(0, 0.018)
        price = max(price, 2.0)
        prices.append(price)

    close = pd.Series(prices, index=dates)
    df = pd.DataFrame(
        {
            "open": close * (1 + np.random.uniform(-0.008, 0.008, days)),
            "high": close * (1 + np.random.uniform(0.001, 0.025, days)),
            "low": close * (1 - np.random.uniform(0.001, 0.025, days)),
            "close": close,
            "volume": np.random.randint(5_000_000, 80_000_000, days).astype(float),
        }
    )
    df.index.name = "datetime"
    print(f"[DataLoader] 模拟数据: {stock_code}, {days}根K线")
    return df
