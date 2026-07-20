"""
backtest/alpha_factor.py
五因子 Alpha 打分模型
KDJ反转 + 成交量 + ROE + 市值 + 均线趋势
"""
import os
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass
import time
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class AlphaScore:
    stock_code: str
    stock_name: str
    total_score: float
    rating: str
    factors: dict = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self):
        return {
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "total_score": round(self.total_score, 1),
            "rating": self.rating,
            "factors": self.factors,
        }

def _get_rating(score: float) -> str:
    if score >= 75: return "重点配置"
    if score >= 60: return "值得关注"
    return "暂不推荐"

def score_stock(stock_code: str, stock_name: str = "") -> AlphaScore:
    """对单只股票打五因子分"""
    try:
        token = os.getenv("TUSHARE_TOKEN", "")
        if not token:
            raise ValueError("未配置TUSHARE_TOKEN")

        from backtest.data_loader import get_stock_data_incremental
        df = get_stock_data_incremental(stock_code, token=token)

        if df is None or len(df) < 30:
            return AlphaScore(stock_code, stock_name, 0, "数据不足", error="数据不足")

        df = df.sort_index()
        close = df["close"]
        volume = df["vol"] if "vol" in df.columns else df.get("volume", None)

        # ── 因子1：KDJ反转（超卖反弹信号）权重25 ──────────────────
        low_min  = df["low"].rolling(9).min()
        high_max = df["high"].rolling(9).max()
        rsv = ((close - low_min) / (high_max - low_min + 1e-9)) * 100
        k = rsv.ewm(com=2).mean()
        d = k.ewm(com=2).mean()
        j = 3 * k - 2 * d

        j_val = float(j.iloc[-1])
        if j_val < 10:      kdj_score = 25
        elif j_val < 20:    kdj_score = 22
        elif j_val < 30:    kdj_score = 18
        elif j_val < 50:    kdj_score = 12
        elif j_val < 70:    kdj_score = 8
        else:               kdj_score = 3

        # ── 因子2：成交量活跃度 权重20 ─────────────────────────────
        if volume is not None and len(volume) >= 20:
            vol_ma20 = volume.rolling(20).mean().iloc[-1]
            vol_now  = float(volume.iloc[-1])
            vol_ratio = vol_now / (vol_ma20 + 1e-9)
            if vol_ratio > 2.0:    vol_score = 20
            elif vol_ratio > 1.5:  vol_score = 17
            elif vol_ratio > 1.0:  vol_score = 13
            elif vol_ratio > 0.7:  vol_score = 9
            else:                  vol_score = 4
        else:
            vol_score = 10  # 无量能数据，给中间分

        # ── 因子3：ROE 估算（用净利润增速代替）权重20 ──────────────
        if len(close) >= 60:
            ret_1m  = float((close.iloc[-1] / close.iloc[-20] - 1) * 100)
            ret_3m  = float((close.iloc[-1] / close.iloc[-60] - 1) * 100)
            momentum = ret_1m * 0.4 + ret_3m * 0.6
            if momentum > 20:    roe_score = 20
            elif momentum > 10:  roe_score = 17
            elif momentum > 0:   roe_score = 13
            elif momentum > -10: roe_score = 8
            else:                roe_score = 3
        else:
            roe_score = 10

        # ── 因子4：市值规模（用收盘价×换手率代替）权重15 ────────────
        price = float(close.iloc[-1])
        if 5 <= price <= 30:     cap_score = 15
        elif 3 <= price < 5:     cap_score = 12
        elif 30 < price <= 100:  cap_score = 12
        elif price > 100:        cap_score = 9
        else:                    cap_score = 5

        # ── 因子5：均线趋势 权重20 ────────────────────────────────
        ma5  = close.rolling(5).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else ma20
        price_now = float(close.iloc[-1])

        trend_signals = 0
        if price_now > float(ma5):  trend_signals += 1
        if price_now > float(ma20): trend_signals += 1
        if float(ma5) > float(ma20): trend_signals += 1
        if float(ma20) > float(ma60): trend_signals += 1

        trend_score = [3, 8, 13, 17, 20][trend_signals]

        # ── 总分 ──────────────────────────────────────────────────
        total = kdj_score + vol_score + roe_score + cap_score + trend_score

        return AlphaScore(
            stock_code=stock_code,
            stock_name=stock_name,
            total_score=float(total),
            rating=_get_rating(total),
            factors={
                "kdj":    {"score": kdj_score,   "j_value": round(j_val, 1)},
                "volume": {"score": vol_score,   "ratio": round(vol_ratio if volume is not None else 1.0, 2)},
                "roe":    {"score": roe_score},
                "market_cap": {"score": cap_score, "price": round(price, 2)},
                "trend":  {"score": trend_score,  "signals": trend_signals},
            }
        )

    except Exception as e:
        return AlphaScore(stock_code, stock_name, 0, "错误", error=str(e))


def batch_score(
    stock_list: list,
    min_score: float = 60.0,
    top_n: int = 15,
) -> list:
    """批量打分，返回评分 >= min_score 的前 top_n 只"""
    results = []
    total = len(stock_list)
    for i, item in enumerate(stock_list):
        code = item[0] if isinstance(item, (list, tuple)) else item
        name = item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else code
        print(f"[Alpha] {i+1}/{total} 打分 {name}({code})...")
        score = score_stock(code, name)
        if not score.error and score.total_score >= min_score:
            results.append(score)
        time.sleep(0.3)  # 限速

    results.sort(key=lambda x: x.total_score, reverse=True)
    return results[:top_n]


def format_score_report(score: AlphaScore) -> str:
    """格式化单只股票的评分报告"""
    f = score.factors
    return f"""## {score.stock_name}({score.stock_code}) Alpha 评分报告

**总分：{score.total_score} / 100** · {score.rating}

| 因子 | 得分 | 说明 |
|------|------|------|
| KDJ超卖反转 | {f.get('kdj',{}).get('score',0)}/25 | J值={f.get('kdj',{}).get('j_value','N/A')} |
| 成交量活跃 | {f.get('volume',{}).get('score',0)}/20 | 量比={f.get('volume',{}).get('ratio','N/A')} |
| 价格动量 | {f.get('roe',{}).get('score',0)}/20 | 近期涨跌表现 |
| 价格区间 | {f.get('market_cap',{}).get('score',0)}/15 | 现价={f.get('market_cap',{}).get('price','N/A')} |
| 均线趋势 | {f.get('trend',{}).get('score',0)}/20 | {f.get('trend',{}).get('signals',0)}/4 指标向上 |
"""
