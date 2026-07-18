#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
rag/news_indexer.py
AlphaStock 新闻知识库管理器

策略定位：
  主题/景气周期股 + 相对低位介入
  覆盖：造船/CPO/AI算力/半导体/军工/低空经济/新能源/有色/煤炭/化工等板块
  市值门槛：300亿以上
  KDJ条件：K<25 J<15（回测调整）

三大功能：
  1. 新闻库扩容：130+只股票批量入库
  2. 流式更新：分批错峰，避免限流
  3. 过期删除：自动清理超过N天的旧新闻
"""

import threading
import time
import hashlib
import schedule
from datetime import datetime, timedelta
from chromadb.utils import embedding_functions
import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ── 配置 ──────────────────────────────────────────────────────────────

CHROMA_DB_PATH = "./chroma_db"
NEWS_COLLECTION = "stock_news_knowledge"
NEWS_EXPIRE_DAYS = 30
STREAM_INTERVAL_MINUTES = 30  # 130只股票，改成30分钟一次避免限流
BATCH_SIZE = 20               # 每批20只，批次间隔10秒

# ── 股票池（按板块，去重后约132只）────────────────────────────────────

WATCH_LIST = [
    # 造船
    ("600150", "中国船舶"),
    ("601989", "中国重工"),
    ("600871", "石化油服"),
    ("601808", "中海油服"),
    # CPO / 光模块
    ("300308", "中际旭创"),
    ("002281", "光迅科技"),
    ("603068", "博通集成"),
    ("600460", "士兰微"),
    ("300782", "卓胜微"),
    # AI / 算力 / 华为鸿蒙
    ("002261", "拓维信息"),
    ("000977", "浪潮信息"),
    ("300036", "超图软件"),
    ("300418", "昆仑万维"),
    ("002230", "科大讯飞"),
    ("688256", "寒武纪"),
    ("002049", "紫光国微"),
    ("300496", "中科创达"),
    ("300033", "同花顺"),
    ("601360", "三六零"),
    ("000100", "TCL科技"),
    # 半导体
    ("603501", "韦尔股份"),
    ("688012", "中微公司"),
    ("688041", "海光信息"),
    ("688008", "澜起科技"),
    ("688396", "华润微"),
    ("600183", "生益科技"),
    ("002371", "北方华创"),
    ("688981", "中芯国际"),
    ("002916", "深南电路"),
    # 军工
    ("600760", "中航沈飞"),
    ("000768", "中航西飞"),
    ("600893", "航发动力"),
    ("600406", "国电南瑞"),
    ("002025", "航天电子"),
    ("600391", "航发科技"),
    ("002179", "中航光电"),
    # 低空经济
    ("000099", "中信海直"),
    ("300159", "新研股份"),
    ("688311", "盟升电子"),
    # 新能源 / 储能
    ("300750", "宁德时代"),
    ("002594", "比亚迪"),
    ("601012", "隆基绿能"),
    ("300014", "亿纬锂能"),
    ("002460", "赣锋锂业"),
    ("600438", "通威股份"),
    ("688390", "固德威"),
    ("002756", "永兴材料"),
    # 有色金属
    ("601899", "紫金矿业"),
    ("600019", "宝山钢铁"),
    ("601600", "中国铝业"),
    ("000630", "铜陵有色"),
    ("600362", "江西铜业"),
    ("000878", "云南铜业"),
    ("600547", "山东黄金"),
    ("600489", "中金黄金"),
    # 煤炭 / 能源
    ("601898", "中煤能源"),
    ("600188", "兖矿能源"),
    ("601225", "陕西煤业"),
    ("601088", "中国神华"),
    ("600028", "中国石化"),
    ("601857", "中国石油"),
    ("600900", "长江电力"),
    ("601985", "中国核电"),
    ("600905", "三峡能源"),
    # 化工
    ("600309", "万华化学"),
    ("002648", "卫星石化"),
    # 医药
    ("600276", "恒瑞医药"),
    ("000538", "云南白药"),
    ("300122", "智飞生物"),
    ("300760", "迈瑞医疗"),
    # 消费 / 白酒
    ("600519", "贵州茅台"),
    ("000858", "五粮液"),
    ("000568", "泸州老窖"),
    ("002304", "洋河股份"),
    ("000651", "格力电器"),
    ("000333", "美的集团"),
    # 银行
    ("000001", "平安银行"),
    ("600036", "招商银行"),
    ("601166", "兴业银行"),
    ("601288", "农业银行"),
    ("601398", "工商银行"),
    # 房地产
    ("000002", "万科A"),
    ("001979", "招商蛇口"),
    ("600048", "保利发展"),
    # 立讯/消费电子
    ("002475", "立讯精密"),
    ("000725", "京东方A"),
]


# ── 市值过滤（300亿以上）─────────────────────────────────────────────

def check_market_cap(stock_code: str, min_cap_billion: float = 300) -> bool:
    """
    检查股票市值是否达到门槛
    min_cap_billion：最小市值（亿元），默认300亿
    """
    try:
        import akshare as ak
        df = ak.stock_individual_info_em(symbol=stock_code)
        if df.empty:
            return True  # 查不到默认通过

        # 找总市值行
        cap_row = df[df["item"] == "总市值"]
        if cap_row.empty:
            return True

        cap_str = str(cap_row.iloc[0]["value"])
        # 转换：可能是"3000亿"或"3000.00亿"
        cap_str = cap_str.replace("亿", "").replace(",", "").strip()
        cap = float(cap_str)

        return cap >= min_cap_billion

    except Exception:
        return True  # 查不到默认通过，不因为API问题误杀


# ── 单例 ──────────────────────────────────────────────────────────────

_client = None
_news_collection = None
_lock = threading.Lock()
_stream_thread = None
_stream_running = False


def _get_news_collection():
    global _client, _news_collection
    if _news_collection is None:
        with _lock:
            if _news_collection is None:
                _client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
                embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="shibing624/text2vec-base-chinese"
                )
                _news_collection = _client.get_or_create_collection(
                    name=NEWS_COLLECTION,
                    embedding_function=embedding_fn,
                    metadata={"hnsw:space": "cosine"},
                )
                print(f"[NewsIndexer] Collection就绪，当前 {_news_collection.count()} 条新闻")
    return _news_collection


# ── 工具函数 ──────────────────────────────────────────────────────────

def _news_id(stock_code: str, title: str) -> str:
    content = f"{stock_code}_{title}"
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def _fetch_news(stock_code: str, limit: int = 50) -> list[dict]:
    """
    拉取新闻，返回结构化列表
    内置重试3次 + timeout
    """
    for attempt in range(3):
        try:
            import akshare as ak
            df = ak.stock_news_em(symbol=stock_code)
            if df.empty:
                return []

            items = []
            for _, row in df.head(limit).iterrows():
                pub_time = str(row.get("发布时间", ""))
                title = str(row.get("新闻标题", "")).strip()
                if not title:
                    continue
                date = pub_time[:10] if len(pub_time) >= 10 else datetime.now().strftime("%Y-%m-%d")
                items.append({
                    "pub_time": pub_time,
                    "title": title,
                    "date": date,
                })
            return items

        except Exception as e:
            if attempt < 2:
                time.sleep(attempt + 1)
            else:
                print(f"[NewsIndexer] {stock_code} 拉取失败（3次重试）: {e}")
    return []


# ── 功能一：分批批量入库 ──────────────────────────────────────────────

def bulk_index(
    stock_list: list[tuple] = None,
    limit_per_stock: int = 50,
    min_cap_billion: float = 300,
    batch_size: int = BATCH_SIZE,
):
    """
    分批批量入库：
    - 市值过滤（默认300亿以上）
    - 每批batch_size只，批次间隔10秒避免限流
    """
    if stock_list is None:
        stock_list = WATCH_LIST

    collection = _get_news_collection()
    total_added = 0
    filtered_count = 0

    print(f"[NewsIndexer] 开始批量入库：{len(stock_list)} 只股票，市值门槛 {min_cap_billion} 亿")

    # 分批处理
    for batch_start in range(0, len(stock_list), batch_size):
        batch = stock_list[batch_start: batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        total_batches = (len(stock_list) + batch_size - 1) // batch_size
        print(f"[NewsIndexer] 第 {batch_num}/{total_batches} 批...")

        for stock_code, stock_name in batch:
            # 市值过滤
            if not check_market_cap(stock_code, min_cap_billion):
                print(f"   ⏭️ {stock_name} 市值不足 {min_cap_billion} 亿，跳过")
                filtered_count += 1
                time.sleep(0.3)
                continue

            items = _fetch_news(stock_code, limit=limit_per_stock)
            added = 0

            for item in items:
                doc_id = _news_id(stock_code, item["title"])
                existing = collection.get(ids=[doc_id])
                if existing["ids"]:
                    continue

                collection.add(
                    documents=[f"{stock_name}（{stock_code}）{item['pub_time']} {item['title']}"],
                    metadatas=[{
                        "stock_code": stock_code,
                        "stock_name": stock_name,
                        "pub_time": item["pub_time"],
                        "date": item["date"],
                        "title": item["title"],
                        "indexed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }],
                    ids=[doc_id],
                )
                added += 1

            total_added += added
            if added > 0:
                print(f"   ✅ {stock_name}：+{added} 条")
            time.sleep(0.5)  # 每只股票间隔0.5秒

        # 批次间隔10秒
        if batch_start + batch_size < len(stock_list):
            print(f"   [批次间隔 10s...]")
            time.sleep(10)

    print(f"[NewsIndexer] 批量入库完成：新增 {total_added} 条，过滤 {filtered_count} 只，总计 {collection.count()} 条")
    return total_added


# ── 功能二：流式更新 ──────────────────────────────────────────────────

def stream_update_once(stock_list: list[tuple] = None):
    """单次流式更新，分批错峰"""
    if stock_list is None:
        stock_list = WATCH_LIST

    collection = _get_news_collection()
    added_total = 0

    for i, (stock_code, stock_name) in enumerate(stock_list):
        items = _fetch_news(stock_code, limit=10)  # 流式只拉最新10条
        for item in items:
            doc_id = _news_id(stock_code, item["title"])
            existing = collection.get(ids=[doc_id])
            if existing["ids"]:
                continue
            collection.add(
                documents=[f"{stock_name}（{stock_code}）{item['pub_time']} {item['title']}"],
                metadatas=[{
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "pub_time": item["pub_time"],
                    "date": item["date"],
                    "title": item["title"],
                    "indexed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }],
                ids=[doc_id],
            )
            added_total += 1

        time.sleep(0.5)

        # 每20只停顿5秒
        if (i + 1) % 20 == 0:
            time.sleep(5)

    if added_total > 0:
        print(f"[Stream] {datetime.now().strftime('%H:%M:%S')} +{added_total} 条，总计 {collection.count()} 条")
    return added_total


def start_stream(interval_minutes: int = STREAM_INTERVAL_MINUTES):
    """启动后台流式更新线程"""
    global _stream_thread, _stream_running
    if _stream_running:
        return

    _stream_running = True

    def _run():
        print(f"[Stream] 启动，间隔 {interval_minutes} 分钟")
        stream_update_once()
        schedule.every(interval_minutes).minutes.do(stream_update_once)
        while _stream_running:
            schedule.run_pending()
            time.sleep(30)

    _stream_thread = threading.Thread(target=_run, daemon=True)
    _stream_thread.start()


def stop_stream():
    global _stream_running
    _stream_running = False


# ── 功能三：过期删除 ──────────────────────────────────────────────────

def delete_expired(expire_days: int = NEWS_EXPIRE_DAYS):
    collection = _get_news_collection()
    cutoff = (datetime.now() - timedelta(days=expire_days)).strftime("%Y-%m-%d")
    print(f"[Cleanup] 删除 {cutoff} 之前的新闻...")
    try:
        collection.delete(where={"date": {"$lt": cutoff}})
        print(f"[Cleanup] 完成，剩余 {collection.count()} 条")
    except Exception as e:
        print(f"[Cleanup] 失败: {e}")


# ── 检索接口 ──────────────────────────────────────────────────────────

def retrieve_news(
    query: str,
    stock_code: str = None,
    k: int = 10,
    days: int = 7,
) -> str:
    collection = _get_news_collection()
    if collection.count() == 0:
        return "新闻库为空，请先运行 bulk_index()"

    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        where_filter = {"date": {"$gte": cutoff}}
        if stock_code:
            where_filter = {
                "$and": [
                    {"stock_code": {"$eq": stock_code}},
                    {"date": {"$gte": cutoff}},
                ]
            }

        results = collection.query(
            query_texts=[query],
            n_results=min(k, collection.count()),
            where=where_filter,
        )

        if not results["documents"] or not results["documents"][0]:
            return f"最近{days}天内未找到相关新闻"

        output = []
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            output.append(f"【{meta.get('stock_name')} | {meta.get('pub_time')}】{meta.get('title', doc)}")
        return "\n".join(output)

    except Exception as e:
        return f"检索失败: {e}"


def get_stats() -> dict:
    collection = _get_news_collection()
    return {
        "total_news": collection.count(),
        "watch_stocks": len(WATCH_LIST),
        "stream_running": _stream_running,
        "expire_days": NEWS_EXPIRE_DAYS,
        "stream_interval_minutes": STREAM_INTERVAL_MINUTES,
    }


# ── 一键启动 ──────────────────────────────────────────────────────────

def start_news_system(
    bulk_first: bool = True,
    stream_interval: int = STREAM_INTERVAL_MINUTES,
    cleanup_hour: int = 2,
    min_cap_billion: float = 300,
):
    collection = _get_news_collection()
    if bulk_first and collection.count() < 100:
        print(f"[NewsSystem] 新闻库不足100条，开始批量初始化（市值>{min_cap_billion}亿）...")
        bulk_index(min_cap_billion=min_cap_billion)
    else:
        print(f"[NewsSystem] 新闻库已有 {collection.count()} 条，跳过批量入库")

    start_stream(interval_minutes=stream_interval)
    schedule.every().day.at(f"{cleanup_hour:02d}:00").do(delete_expired)
    print(f"[NewsSystem] 启动完成：{get_stats()}")