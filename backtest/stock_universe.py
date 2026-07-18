#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
backtest/stock_universe.py
股票池管理

两种模式：
  1. 静态板块池（已有的STOCK_UNIVERSE，快速启动用）
  2. 动态全量池（从akshare拉A股全量，按市值筛选2000只）

本地缓存：
  缓存到 ./cache/stock_universe_cache.json
  每天更新一次，避免重复拉取
"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

# ── 缓存配置 ──────────────────────────────────────────────────────────
CACHE_DIR = Path("./cache")
CACHE_FILE = CACHE_DIR / "stock_universe_cache.json"
CACHE_EXPIRE_HOURS = 24  # 缓存24小时

# ── 静态板块池（原有，快速启动用）────────────────────────────────────
STOCK_UNIVERSE = {
    "CPO光模块": {
        "600487": "亨通光电", "301205": "联特科技", "300814": "中富电路",
        "600522": "中天科技", "600498": "烽火通信", "300394": "天孚通信",
        "002475": "立讯精密", "300502": "新易盛", "601138": "工业富联",
        "300308": "中际旭创", "600584": "长电科技", "301165": "锐捷网络",
        "002281": "光迅科技", "002429": "兆驰股份", "002179": "中航光电",
        "000988": "华工科技", "002185": "华天科技",
    },
    "PCB": {
        "002916": "深南电路", "600183": "生益科技", "002463": "沪电股份",
        "603228": "景旺电子", "002649": "博敏电子",
    },
    "半导体": {
        "688012": "中微公司", "688008": "澜起科技", "300661": "圣邦股份",
        "603986": "兆易创新", "002371": "北方华创", "688019": "安集科技",
        "300666": "江丰电子", "688347": "华虹公司", "688041": "海光信息",
        "688256": "寒武纪", "603501": "韦尔股份", "688981": "中芯国际",
        "688126": "沪硅产业", "002049": "紫光国微", "688396": "华润微",
        "300316": "晶盛机电",
    },
    "AI算力": {
        "688041": "海光信息", "300308": "中际旭创", "300502": "新易盛",
        "688256": "寒武纪", "301165": "锐捷网络", "002371": "北方华创",
        "601138": "工业富联", "002261": "拓维信息", "000977": "浪潮信息",
        "002230": "科大讯飞", "300033": "同花顺", "601360": "三六零",
        "000100": "TCL科技",
    },
    "造船": {
        "600150": "中国船舶", "601989": "中国重工",
        "600871": "石化油服", "601808": "中海油服",
    },
    "军工": {
        "600760": "中航沈飞", "000768": "中航西飞", "600893": "航发动力",
        "600406": "国电南瑞", "002025": "航天电子", "600391": "航发科技",
        "002179": "中航光电",
    },
    "低空经济": {
        "000099": "中信海直", "300159": "新研股份", "688311": "盟升电子",
    },
    "新能源储能": {
        "300750": "宁德时代", "002594": "比亚迪", "601012": "隆基绿能",
        "300014": "亿纬锂能", "002460": "赣锋锂业", "600438": "通威股份",
        "002074": "国轩高科", "300207": "欣旺达", "002812": "恩捷股份",
    },
    "有色金属": {
        "601899": "紫金矿业", "600019": "宝山钢铁", "601600": "中国铝业",
        "000630": "铜陵有色", "600362": "江西铜业", "000878": "云南铜业",
        "600547": "山东黄金", "600489": "中金黄金", "603993": "洛阳钼业",
        "002460": "赣锋锂业", "603799": "华友钴业",
    },
    "煤炭能源": {
        "601898": "中煤能源", "600188": "兖矿能源", "601225": "陕西煤业",
        "601088": "中国神华", "600028": "中国石化", "601857": "中国石油",
        "600900": "长江电力", "601985": "中国核电", "600905": "三峡能源",
    },
    "化工": {
        "600309": "万华化学", "002648": "卫星石化",
    },
    "医药": {
        "600276": "恒瑞医药", "000538": "云南白药",
        "300122": "智飞生物", "300760": "迈瑞医疗",
    },
    "消费白酒": {
        "600519": "贵州茅台", "000858": "五粮液", "000568": "泸州老窖",
        "002304": "洋河股份", "000651": "格力电器", "000333": "美的集团",
    },
    "银行": {
        "000001": "平安银行", "600036": "招商银行", "601166": "兴业银行",
        "601288": "农业银行", "601398": "工商银行",
    },
    "机器人": {
        "300124": "汇川技术", "002415": "海康威视", "300450": "先导智能",
    },
}

# 展平成完整股票列表
ALL_STOCKS = {}
for sector, stocks in STOCK_UNIVERSE.items():
    for code, name in stocks.items():
        ALL_STOCKS[code] = {"name": name, "sector": sector}


# ── 本地缓存 ──────────────────────────────────────────────────────────

def _load_cache() -> dict | None:
    """加载本地缓存，过期返回None"""
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
        if datetime.now() - cached_at > timedelta(hours=CACHE_EXPIRE_HOURS):
            return None
        return cache.get("data")
    except Exception:
        return None


def _save_cache(data: list[dict]):
    """保存到本地缓存"""
    CACHE_DIR.mkdir(exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "cached_at": datetime.now().isoformat(),
            "count": len(data),
            "data": data,
        }, f, ensure_ascii=False, indent=2)
    print(f"[StockUniverse] 缓存已保存：{len(data)} 只股票 → {CACHE_FILE}")


# ── 动态全量股票池 ────────────────────────────────────────────────────

def get_dynamic_universe(
    max_stocks: int = 5000,
    use_cache: bool = True,
    cache_days: int = 30,
) -> list[tuple[str, str]]:
    """
    获取A股全量股票列表（只存代码+名称，不做市值筛选）

    设计原则：
      - 只拉一次，缓存30天（股票代码和名称很少变化）
      - 不在这里做市值筛选（市值每天变，按需查）
      - 市值校验在用户分析具体股票时实时判断

    Args:
        max_stocks: 最多返回多少只，默认5000
        use_cache: 是否使用本地缓存
        cache_days: 缓存有效天数，默认30天

    Returns:
        [(stock_code, stock_name), ...]
    """
    global CACHE_EXPIRE_HOURS
    CACHE_EXPIRE_HOURS = cache_days * 24  # 动态调整缓存周期

    # 先查缓存
    if use_cache:
        cached = _load_cache()
        if cached:
            print(f"[StockUniverse] 命中缓存：{len(cached)} 只股票")
            return [(item["code"], item["name"]) for item in cached[:max_stocks]]

    print(f"[StockUniverse] 缓存未命中，从akshare拉取A股全量列表...")

    try:
        import akshare as ak

        # 只拉代码+名称，不拉市值（减少数据量，加快速度）
        df = ak.stock_info_a_code_name()

        if df.empty:
            print("[StockUniverse] akshare返回空数据，使用静态池")
            return get_static_universe()

        # 标准化列名
        df.columns = [c.strip() for c in df.columns]
        if "code" not in df.columns:
            # 尝试其他常见列名
            for col in df.columns:
                if "代码" in col or "code" in col.lower():
                    df = df.rename(columns={col: "code"})
                    break
        if "name" not in df.columns:
            for col in df.columns:
                if "名称" in col or "name" in col.lower():
                    df = df.rename(columns={col: "name"})
                    break

        if "code" not in df.columns or "name" not in df.columns:
            print(f"[StockUniverse] 列名异常：{df.columns.tolist()}，使用静态池")
            return get_static_universe()

        # 过滤ST和退市
        df = df[~df["name"].str.contains("ST|退|\*", na=False)]

        # 过滤北交所（8开头/4开头）
        df = df[~df["code"].str.startswith(("8", "4"))]

        result_df = df.head(max_stocks)[["code", "name"]]

        # 保存缓存（30天有效）
        cache_data = result_df.to_dict("records")
        _save_cache(cache_data)

        result = [(row["code"], row["name"]) for _, row in result_df.iterrows()]
        print(f"[StockUniverse] 拉取完成：{len(result)} 只股票，缓存{cache_days}天")
        return result

    except Exception as e:
        print(f"[StockUniverse] akshare拉取失败: {e}，使用静态池")
        return get_static_universe()


def check_stock_eligibility(stock_code: str, min_cap_billion: float = 300) -> tuple[bool, str]:
    """
    按需检查单只股票是否满足策略条件
    在用户分析具体股票时调用，不做批量检查

    Args:
        stock_code: 股票代码
        min_cap_billion: 最小市值（亿元）

    Returns:
        (是否满足条件, 原因说明)
    """
    try:
        import akshare as ak
        import time

        # 拉取个股实时信息（含市值）
        df = ak.stock_individual_info_em(symbol=stock_code)
        if df.empty:
            return True, "市值信息获取失败，默认通过"

        # 找总市值
        cap_row = df[df.iloc[:, 0].astype(str).str.contains("总市值", na=False)]
        if cap_row.empty:
            return True, "市值字段未找到，默认通过"

        cap_str = str(cap_row.iloc[0, 1]).replace("亿", "").replace(",", "").strip()
        try:
            cap = float(cap_str)
        except ValueError:
            return True, f"市值格式异常（{cap_str}），默认通过"

        if cap < min_cap_billion:
            return False, f"市值{cap:.0f}亿，低于门槛{min_cap_billion}亿"

        # 检查ST
        name_row = df[df.iloc[:, 0].astype(str).str.contains("股票简称|名称", na=False)]
        if not name_row.empty:
            name = str(name_row.iloc[0, 1])
            if "ST" in name or "*" in name:
                return False, f"ST股票（{name}），不在策略范围"

        return True, f"市值{cap:.0f}亿，满足条件"

    except Exception as e:
        return True, f"市值检查异常（{e}），默认通过"


def get_static_universe() -> list[tuple[str, str]]:
    """返回静态板块池（兜底方案）"""
    result = [(code, info["name"]) for code, info in ALL_STOCKS.items()]
    print(f"[StockUniverse] 使用静态池：{len(result)} 只股票")
    return result


def get_sector_stocks(sector: str) -> dict:
    return STOCK_UNIVERSE.get(sector, {})


def get_all_stocks() -> dict:
    return ALL_STOCKS


def list_sectors() -> list:
    return list(STOCK_UNIVERSE.keys())


def clear_cache():
    """清除本地缓存，下次强制重新拉取"""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
        print(f"[StockUniverse] 缓存已清除")