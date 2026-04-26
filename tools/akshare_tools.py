import re
import time
from datetime import datetime, timedelta
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

def _normalize_symbol(symbol: str) -> str:
    return (symbol or "").strip()


def _get_spot_row_from_akshare(symbol: str) -> pd.Series | None:
    """
    用 AKShare 东财实时行情接口获取单只 A 股的行情行。
    返回匹配到的单行 Series，失败返回 None。
    """
    try:
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            print(f"[AKSHARE_SPOT] empty result for symbol={symbol}")
            return None

        print(f"[AKSHARE_SPOT] columns={list(df.columns)}")
        if "代码" not in df.columns:
            print(f"[AKSHARE_SPOT] missing '代码' column for symbol={symbol}")
            return None

        matched = df[df["代码"].astype(str).str.zfill(6) == symbol]
        if matched.empty:
            print(f"[AKSHARE_SPOT] no matched row for symbol={symbol}")
            return None

        print(f"[AKSHARE_SPOT] matched symbol={symbol}")
        return matched.iloc[0]

    except Exception as e:
        print(f"[AKSHARE_SPOT] exception for symbol={symbol}: {type(e).__name__}: {str(e)}")
        return None


def _get_hist_from_akshare(symbol: str, days: int) -> pd.DataFrame:
    """
    用 AKShare 历史行情接口获取最近 N 天日线。
    返回统一列名的数据框；失败返回空 DataFrame。
    """
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=max(days * 3, 90))

        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            adjust="qfq",
        )

        if df is None or df.empty:
            return pd.DataFrame()

        rename_map = {
            "日期": "日期",
            "开盘": "开盘",
            "收盘": "收盘",
            "最高": "最高",
            "最低": "最低",
            "成交量": "成交量",
            "涨跌幅": "涨跌幅",
        }
        available = [c for c in rename_map if c in df.columns]
        if not available:
            return pd.DataFrame()

        df = df[available].copy()
        df["日期"] = df["日期"].astype(str)

        # 保证关键列是数值型
        for col in ["开盘", "收盘", "最高", "最低", "成交量"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # 只保留最近 days 条
        df = df.tail(days).reset_index(drop=True)
        return df

    except Exception:
        return pd.DataFrame()

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
    优先 AKShare；失败再回退到 yfinance。
    """
    symbol = _normalize_symbol(symbol)

    err = _validate_symbol(symbol)
    if err:
        return _error("get_stock_price", symbol, err)

    # ---------- 方案A：优先 AKShare ----------
    try:
        row = _get_spot_row_from_akshare(symbol)
        if row is not None:
            stock_name = str(row.get("名称", "名称未验证")).strip() or "名称未验证"

            latest_price = _safe_float(row.get("最新价"))
            change_pct = _safe_float(row.get("涨跌幅"))
            volume = _safe_float(row.get("成交量"))
            market_cap = row.get("总市值", "N/A")
            turnover = row.get("换手率", "N/A")

            if latest_price is not None:
                body = (
                    f"股票名称：{stock_name}\n"
                    f"最新价：{latest_price:.2f}\n"
                    f"涨跌幅：{change_pct if change_pct is not None else 'N/A'}\n"
                    f"成交量：{volume if volume is not None else 'N/A'}\n"
                    f"总市值：{market_cap}\n"
                    f"换手率：{turnover}\n"
                    f"数据来源：AKShare/东方财富实时行情"
                )
                return _ok("get_stock_price", symbol, body)
    except Exception:
        pass

    # ---------- 方案B：回退 yfinance ----------
    try:
        yf_symbol = _to_yf_symbol(symbol)
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period="5d")

        if df.empty:
            return _error("get_stock_price", symbol, "AKShare 与 yfinance 均未获取到行情数据")

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
            f"数据来源：yfinance 回退链路"
        )
        return _ok("get_stock_price", symbol, body)

    except Exception as e:
        return _error("get_stock_price", symbol, f"{type(e).__name__}: {str(e)}")


@tool
def get_financial_indicator(symbol: str) -> str:
    """
    获取A股股票核心财务指标。
    优先使用 AKShare/行情工具里的中文股票名称；
    财务字段仍主要来自 yfinance.info。
    symbol: 股票代码，如 '002218'
    """
    symbol = (symbol or "").strip()

    err = _validate_symbol(symbol)
    if err:
        return _error("get_financial_indicator", symbol, err)

    try:
        # 1) 先尝试从 AKShare 直接获取中文股票名称
        ak_name = None
        try:
            row = _get_spot_row_from_akshare(symbol)
            if row is not None:
                ak_name = str(row.get("名称", "")).strip() or None
        except Exception:
            ak_name = None

        # 2) 如果 AKShare 直接名称没拿到，再从 get_stock_price 的结果里解析中文名
        if not ak_name:
            try:
                price_result = get_stock_price.invoke({"symbol": symbol})
                if "[TOOL_OK]" in price_result:
                    for line in price_result.splitlines():
                        if line.startswith("股票名称："):
                            parsed_name = line.replace("股票名称：", "").strip()
                            if parsed_name and parsed_name != "名称未验证":
                                ak_name = parsed_name
                                break
            except Exception:
                pass

        # 3) 再从 yfinance 获取财务字段
        yf_symbol = _to_yf_symbol(symbol)
        ticker = yf.Ticker(yf_symbol)

        try:
            info = ticker.info or {}
        except Exception as e:
            return _error(
                "get_financial_indicator",
                symbol,
                f"财务信息拉取失败：{type(e).__name__}: {str(e)}"
            )

        if not info:
            return _error("get_financial_indicator", symbol, "财务信息为空")

        # 4) 名称优先使用中文名，英文名仅作最后回退
        stock_name = (
            ak_name
            or info.get("longName")
            or info.get("shortName")
            or "名称未验证"
        )

        current_price = info.get("currentPrice", "N/A")
        trailing_pe = info.get("trailingPE", "N/A")
        price_to_book = info.get("priceToBook", "N/A")
        market_cap = info.get("marketCap", "N/A")
        roe = info.get("returnOnEquity", "N/A")
        revenue_growth = info.get("revenueGrowth", "N/A")
        gross_margins = info.get("grossMargins", "N/A")
        debt_to_equity = info.get("debtToEquity", "N/A")
        industry = info.get("industry", "N/A")

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
            f"说明：股票名称优先采用 AKShare 中文简称；若部分字段为 N/A，表示数据源未提供，不得自行补全。"
        )
        return _ok("get_financial_indicator", symbol, body)

    except Exception as e:
        return _error("get_financial_indicator", symbol, f"{type(e).__name__}: {str(e)}")


@tool
def get_stock_history(symbol: str, days: int = 30) -> str:
    """
    获取A股股票最近N天历史K线数据。
    优先 AKShare；失败再回退到 yfinance。
    """
    symbol = _normalize_symbol(symbol)

    err = _validate_symbol(symbol)
    if err:
        return _error("get_stock_history", symbol, err)

    if days <= 1 or days > 365:
        return _error("get_stock_history", symbol, "days 参数不合理，应在 2 到 365 之间")

    # ---------- 方案A：优先 AKShare ----------
    try:
        df = _get_hist_from_akshare(symbol, days)

        if not df.empty:
            required_cols = {"日期", "开盘", "收盘", "最高", "最低", "成交量"}
            if required_cols.issubset(set(df.columns)):
                if df["收盘"].isna().all():
                    return _error("get_stock_history", symbol, "AKShare 历史收盘价全部为空或NaN")

                if "涨跌幅" not in df.columns:
                    df["涨跌幅"] = df["收盘"].pct_change(fill_method=None) * 100

                latest_close = _safe_float(df["收盘"].iloc[-1])
                highest = _safe_float(df["最高"].max())
                lowest = _safe_float(df["最低"].min())

                if latest_close is not None and highest is not None and lowest is not None:
                    df_view = df[["日期", "开盘", "收盘", "最高", "最低", "成交量", "涨跌幅"]].tail(10)
                    body = (
                        f"最近{len(df)}天K线数据\n"
                        f"期间最高价：{highest:.2f}\n"
                        f"期间最低价：{lowest:.2f}\n"
                        f"最新收盘价：{latest_close:.2f}\n"
                        f"数据来源：AKShare/东方财富历史行情\n\n"
                        f"最近10日明细：\n{df_view.to_string(index=False)}"
                    )
                    return _ok("get_stock_history", symbol, body)
    except Exception:
        pass

    # ---------- 方案B：回退 yfinance ----------
    try:
        date_key = datetime.now().strftime("%Y%m%d%H")
        df = _get_stock_history_cached(symbol, days, date_key)

        if df.empty:
            return _error("get_stock_history", symbol, "AKShare 与 yfinance 均未获取到历史K线数据")

        required_cols = {"日期", "开盘", "收盘", "最高", "最低", "成交量"}
        if not required_cols.issubset(set(df.columns)):
            return _error("get_stock_history", symbol, "历史数据字段不完整")

        if df["收盘"].isna().all():
            return _error("get_stock_history", symbol, "历史收盘价全部为空或NaN")

        if df[["开盘", "收盘", "最高", "最低"]].isna().any().any():
            return _error("get_stock_history", symbol, "关键价格字段存在空值，无法生成技术摘要")

        df["涨跌幅"] = df["收盘"].pct_change(fill_method=None) * 100

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
            f"最新收盘价：{latest_close:.2f}\n"
            f"数据来源：yfinance 回退链路\n\n"
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