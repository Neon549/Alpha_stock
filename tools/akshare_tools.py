import re
import time
from datetime import datetime
from functools import lru_cache

import akshare as ak
import pandas as pd
import requests
import yfinance as yf
from langchain_core.tools import tool

# ============================================================
# 统一说明
# 1. 成功返回必须带 [TOOL_OK]
# 2. 失败返回必须带 [TOOL_ERROR]
# 3. 失败时明确说明：数据不足，禁止基于假设继续分析
# ============================================================

# 设置全局 User-Agent，尽量减少数据源拦截问题
session = requests.Session()
session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
)
ak.requests_session = session


def _error(tool_name: str, symbol: str, reason: str) -> str:
    return (
        f"[TOOL_ERROR]\n"
        f"tool={tool_name}\n"
        f"symbol={symbol}\n"
        f"reason={reason}\n"
        f"结论：数据不足，禁止基于假设继续分析。"
    )


def _ok(tool_name: str, symbol: str, body: str) -> str:
    return f"[TOOL_OK]\ntool={tool_name}\nsymbol={symbol}\n{body}"


def _validate_symbol(symbol: str) -> str | None:
    symbol = (symbol or "").strip()
    if not re.fullmatch(r"\d{6}", symbol):
        return "股票代码格式错误，应为6位数字"
    if symbol[0] not in {"0", "3", "6"}:
        return "当前仅支持A股常见6位代码（0/3/6开头）"
    return None


def _to_yf_symbol(symbol: str) -> str:
    return f"{symbol}.SS" if symbol.startswith("6") else f"{symbol}.SZ"


def _safe_float(value):
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


@lru_cache(maxsize=128)
def _get_stock_history_cached(symbol: str, days: int, date_key: str) -> pd.DataFrame:
    """
    使用 yfinance 获取历史数据。
    date_key 用于按小时刷新缓存，避免长期脏缓存。
    """
    try:
        yf_symbol = _to_yf_symbol(symbol)
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=f"{days}d")

        if df.empty:
            return pd.DataFrame()

        required_cols = {"Open", "Close", "High", "Low", "Volume"}
        if not required_cols.issubset(set(df.columns)):
            return pd.DataFrame()

        df = df.rename(
            columns={
                "Open": "开盘",
                "Close": "收盘",
                "High": "最高",
                "Low": "最低",
                "Volume": "成交量",
            }
        )

        df.index = df.index.strftime("%Y-%m-%d")
        df.index.name = "日期"
        df = df.reset_index()

        return df
    except Exception:
        return pd.DataFrame()


@tool
def get_stock_price(symbol: str) -> str:
    """
    获取A股股票最近行情数据。
    symbol: 股票代码，如 '002218'
    """
    symbol = (symbol or "").strip()

    err = _validate_symbol(symbol)
    if err:
        return _error("get_stock_price", symbol, err)

    try:
        yf_symbol = _to_yf_symbol(symbol)
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period="5d")

        if df.empty:
            return _error("get_stock_price", symbol, "行情数据为空，可能代码错误、停牌或数据源不可用")

        if len(df) < 2:
            return _error("get_stock_price", symbol, "可用交易日不足2天，无法计算涨跌幅")

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        latest_close = _safe_float(latest.get("Close"))
        prev_close = _safe_float(prev.get("Close"))
        latest_volume = _safe_float(latest.get("Volume"))

        if latest_close is None:
            return _error("get_stock_price", symbol, "最新收盘价为空或NaN")
        if prev_close is None or prev_close == 0:
            return _error("get_stock_price", symbol, "前一日收盘价无效，无法计算涨跌幅")
        if latest_volume is None:
            return _error("get_stock_price", symbol, "最新成交量为空或NaN")

        change_pct = (latest_close - prev_close) / prev_close * 100

        info = {}
        try:
            info = ticker.info or {}
        except Exception:
            info = {}

        stock_name = info.get("longName") or info.get("shortName") or "名称未验证"
        industry = info.get("industry", "N/A")
        market_cap = info.get("marketCap", "N/A")

        body = (
            f"股票名称：{stock_name}\n"
            f"最新价：{latest_close:.2f}\n"
            f"涨跌幅：{change_pct:.2f}%\n"
            f"成交量：{latest_volume:,.0f}\n"
            f"总市值：{market_cap}\n"
            f"行业：{industry}\n"
            f"数据日期：{df.index[-1] if hasattr(df.index[-1], 'strftime') else '最近交易日'}"
        )
        return _ok("get_stock_price", symbol, body)

    except Exception as e:
        return _error("get_stock_price", symbol, f"{type(e).__name__}: {str(e)}")


@tool
def get_financial_indicator(symbol: str) -> str:
    """
    获取A股股票核心财务指标。
    symbol: 股票代码，如 '002218'
    """
    symbol = (symbol or "").strip()

    err = _validate_symbol(symbol)
    if err:
        return _error("get_financial_indicator", symbol, err)

    try:
        yf_symbol = _to_yf_symbol(symbol)
        ticker = yf.Ticker(yf_symbol)

        try:
            info = ticker.info or {}
        except Exception as e:
            return _error("get_financial_indicator", symbol, f"财务信息拉取失败：{type(e).__name__}: {str(e)}")

        if not info:
            return _error("get_financial_indicator", symbol, "财务信息为空")

        stock_name = info.get("longName") or info.get("shortName") or "名称未验证"

        current_price = info.get("currentPrice", "N/A")
        trailing_pe = info.get("trailingPE", "N/A")
        price_to_book = info.get("priceToBook", "N/A")
        market_cap = info.get("marketCap", "N/A")
        roe = info.get("returnOnEquity", "N/A")
        revenue_growth = info.get("revenueGrowth", "N/A")
        gross_margins = info.get("grossMargins", "N/A")
        debt_to_equity = info.get("debtToEquity", "N/A")
        industry = info.get("industry", "N/A")

        # 至少保证不是全空
        core_values = [
            current_price,
            trailing_pe,
            price_to_book,
            market_cap,
            roe,
            revenue_growth,
            gross_margins,
            debt_to_equity,
        ]
        non_empty_count = sum(v not in [None, "N/A"] for v in core_values)

        if non_empty_count == 0:
            return _error("get_financial_indicator", symbol, "关键财务字段全部为空")

        body = (
            f"股票名称：{stock_name}\n"
            f"最新价：{current_price}\n"
            f"市盈率(PE)：{trailing_pe}\n"
            f"市净率(PB)：{price_to_book}\n"
            f"总市值：{market_cap}\n"
            f"ROE：{roe}\n"
            f"营收增长率：{revenue_growth}\n"
            f"毛利率：{gross_margins}\n"
            f"负债率：{debt_to_equity}\n"
            f"行业：{industry}\n"
            f"说明：若部分字段为 N/A，表示数据源未提供，不得自行补全。"
        )
        return _ok("get_financial_indicator", symbol, body)

    except Exception as e:
        return _error("get_financial_indicator", symbol, f"{type(e).__name__}: {str(e)}")


@tool
def get_stock_history(symbol: str, days: int = 30) -> str:
    """
    获取A股股票最近N天历史K线数据。
    symbol: 股票代码，如 '002218'
    days: 天数，默认30
    """
    symbol = (symbol or "").strip()

    err = _validate_symbol(symbol)
    if err:
        return _error("get_stock_history", symbol, err)

    if days <= 1 or days > 365:
        return _error("get_stock_history", symbol, "days 参数不合理，应在 2 到 365 之间")

    try:
        date_key = datetime.now().strftime("%Y%m%d%H")
        df = _get_stock_history_cached(symbol, days, date_key)

        if df.empty:
            return _error("get_stock_history", symbol, "历史K线数据为空")

        required_cols = {"日期", "开盘", "收盘", "最高", "最低", "成交量"}
        if not required_cols.issubset(set(df.columns)):
            return _error("get_stock_history", symbol, "历史数据字段不完整")

        if df["收盘"].isna().all():
            return _error("get_stock_history", symbol, "历史收盘价全部为空或NaN")

        df["涨跌幅"] = df["收盘"].pct_change() * 100

        latest_close = _safe_float(df["收盘"].iloc[-1])
        highest = _safe_float(df["最高"].max())
        lowest = _safe_float(df["最低"].min())

        if latest_close is None or highest is None or lowest is None:
            return _error("get_stock_history", symbol, "关键价格字段存在空值，无法生成技术摘要")

        cols = ["日期", "开盘", "收盘", "最高", "最低", "成交量", "涨跌幅"]
        df_view = df[cols].tail(10)

        body = (
            f"最近{len(df)}天K线数据\n"
            f"期间最高价：{highest:.2f}\n"
            f"期间最低价：{lowest:.2f}\n"
            f"最新收盘价：{latest_close:.2f}\n\n"
            f"最近10日明细：\n{df_view.to_string(index=False)}"
        )
        return _ok("get_stock_history", symbol, body)

    except Exception as e:
        return _error("get_stock_history", symbol, f"{type(e).__name__}: {str(e)}")


@tool
def get_stock_news(symbol: str) -> str:
    """
    获取A股股票相关新闻。
    symbol: 股票代码，如 '002218'
    """
    symbol = (symbol or "").strip()

    err = _validate_symbol(symbol)
    if err:
        return _error("get_stock_news", symbol, err)

    try:
        time.sleep(1)
        df = ak.stock_news_em(symbol=symbol)

        if df.empty:
            return _error("get_stock_news", symbol, "未找到相关新闻")

        required_cols = {"发布时间", "新闻标题"}
        if not required_cols.issubset(set(df.columns)):
            return _error("get_stock_news", symbol, "新闻数据字段不完整")

        news_list = []
        for _, row in df.head(5).iterrows():
            news_time = row.get("发布时间", "")
            news_title = row.get("新闻标题", "")
            if not news_title:
                continue
            news_list.append(f"【{news_time}】{news_title}")

        if not news_list:
            return _error("get_stock_news", symbol, "新闻列表为空")

        body = "最新资讯：\n" + "\n".join(news_list)
        return _ok("get_stock_news", symbol, body)

    except Exception as e:
        return _error("get_stock_news", symbol, f"{type(e).__name__}: {str(e)}")


ALL_TOOLS = [
    get_stock_price,
    get_stock_history,
    get_financial_indicator,
    get_stock_news,
]