#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@author: yulin
@created: 2026/7/17 10:28
@updated: 2026/7/17 10:28
@version: 1.0
@description: 
"""
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
rag/news_indexer.py
新闻知识库管理器

三大功能：
  1. 新闻库扩容：支持上百只股票批量入库
  2. 流式更新：新闻实时入库（每N分钟轮询）
  3. 过期删除：自动清理超过N天的旧新闻

独立于 strategy_indexer.py，使用单独的 ChromaDB Collection
Collection名：stock_news_knowledge
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

# 新闻保留天数：超过这个天数的新闻自动删除
NEWS_EXPIRE_DAYS = 30

# 流式更新间隔（分钟）
STREAM_INTERVAL_MINUTES = 5

# 扩容目标股票池（可以继续扩展）
WATCH_LIST = [
    # 银行
    ("000001", "平安银行"),
    ("600036", "招商银行"),
    ("601166", "兴业银行"),
    ("600000", "浦发银行"),
    # 消费
    ("600519", "贵州茅台"),
    ("000858", "五粮液"),
    ("000651", "格力电器"),
    ("000333", "美的集团"),
    # 科技
    ("000725", "京东方A"),
    ("002475", "立讯精密"),
    ("603501", "韦尔股份"),
    # 新能源
    ("300750", "宁德时代"),
    ("002594", "比亚迪"),
    ("601012", "隆基绿能"),
    # 地产
    ("000002", "万科A"),
    ("001979", "招商蛇口"),
    # 医药
    ("600276", "恒瑞医药"),
    ("000538", "云南白药"),
]

# ── 单例 ──────────────────────────────────────────────────────────────

_client = None
_news_collection = None
_lock = threading.Lock()
_stream_thread = None
_stream_running = False


def _get_news_collection():
    """获取新闻 ChromaDB collection（单例）"""
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
    """
    用股票代码+标题生成唯一ID
    相同新闻不会重复入库
    """
    content = f"{stock_code}_{title}"
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def _parse_news(raw_news: str, stock_code: str, stock_name: str) -> list[dict]:
    """
    把 get_stock_news 的返回字符串解析成结构化列表
    格式：【2024-01-15 10:30:00】新闻标题
    """
    items = []
    for line in raw_news.strip().split("\n"):
        line = line.strip()
        if not line or not line.startswith("【"):
            continue

        try:
            # 提取时间和标题
            end_bracket = line.index("】")
            pub_time = line[1:end_bracket].strip()
            title = line[end_bracket + 1:].strip()

            if not title:
                continue

            items.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "pub_time": pub_time,
                "title": title,
                "full_text": f"{stock_name}（{stock_code}）{pub_time} {title}",
                "date": pub_time[:10] if len(pub_time) >= 10 else datetime.now().strftime("%Y-%m-%d"),
            })
        except (ValueError, IndexError):
            continue

    return items


def _fetch_news(stock_code: str) -> str:
    """拉取新闻，返回原始字符串"""
    try:
        import akshare as ak
        import time as _time
        _time.sleep(0.5)  # 避免限流

        df = ak.stock_news_em(symbol=stock_code)
        if df.empty:
            return ""

        news_list = []
        # 拉取最新50条（扩容）
        for _, row in df.head(50).iterrows():
            pub_time = row.get("发布时间", "")
            title = row.get("新闻标题", "")
            if title:
                news_list.append(f"【{pub_time}】{title}")

        return "\n".join(news_list)

    except Exception as e:
        print(f"[NewsIndexer] 拉取 {stock_code} 新闻失败: {e}")
        return ""


# ── 功能一：批量入库（扩容）────────────────────────────────────────────

def bulk_index(stock_list: list[tuple] = None, limit_per_stock: int = 50):
    """
    批量入库：对 WATCH_LIST 所有股票拉取新闻并入库

    Args:
        stock_list: 股票列表，默认用 WATCH_LIST
        limit_per_stock: 每只股票最多入库多少条，默认50
    """
    if stock_list is None:
        stock_list = WATCH_LIST

    collection = _get_news_collection()
    total_added = 0
    total_skipped = 0

    print(f"[NewsIndexer] 开始批量入库，目标：{len(stock_list)} 只股票")

    for stock_code, stock_name in stock_list:
        try:
            raw = _fetch_news(stock_code)
            if not raw:
                print(f"   ⚠️ {stock_name} 无新闻，跳过")
                continue

            items = _parse_news(raw, stock_code, stock_name)
            added = 0

            for item in items[:limit_per_stock]:
                doc_id = _news_id(stock_code, item["title"])

                # 去重检查
                existing = collection.get(ids=[doc_id])
                if existing["ids"]:
                    total_skipped += 1
                    continue

                # 入库
                collection.add(
                    documents=[item["full_text"]],
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
            print(f"   ✅ {stock_name}：新增 {added} 条，跳过重复 {total_skipped} 条")

        except Exception as e:
            print(f"   ❌ {stock_name} 入库失败: {e}")

        time.sleep(0.5)  # 避免限流

    print(f"[NewsIndexer] 批量入库完成：新增 {total_added} 条，总计 {collection.count()} 条")
    return total_added


# ── 功能二：流式更新 ──────────────────────────────────────────────────

def stream_update_once(stock_list: list[tuple] = None):
    """
    单次流式更新：拉取所有股票最新新闻，只入库新增的
    每次调用只处理新数据，不重复
    """
    if stock_list is None:
        stock_list = WATCH_LIST

    collection = _get_news_collection()
    added_total = 0

    for stock_code, stock_name in stock_list:
        try:
            raw = _fetch_news(stock_code)
            if not raw:
                continue

            items = _parse_news(raw, stock_code, stock_name)

            for item in items:
                doc_id = _news_id(stock_code, item["title"])

                # 去重：已有的跳过
                existing = collection.get(ids=[doc_id])
                if existing["ids"]:
                    continue

                # 新增入库
                collection.add(
                    documents=[item["full_text"]],
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

        except Exception as e:
            print(f"[Stream] {stock_name} 更新失败: {e}")

    if added_total > 0:
        print(f"[Stream] {datetime.now().strftime('%H:%M:%S')} 新增 {added_total} 条，总计 {collection.count()} 条")

    return added_total


def start_stream(interval_minutes: int = STREAM_INTERVAL_MINUTES):
    """
    启动后台流式更新线程
    每 interval_minutes 分钟自动拉取一次新新闻入库

    Args:
        interval_minutes: 更新间隔，默认5分钟
    """
    global _stream_thread, _stream_running

    if _stream_running:
        print("[Stream] 流式更新已在运行")
        return

    _stream_running = True

    def _run():
        print(f"[Stream] 启动流式更新，间隔 {interval_minutes} 分钟")

        # 启动时立刻跑一次
        stream_update_once()

        # 之后按间隔定时跑
        schedule.every(interval_minutes).minutes.do(stream_update_once)

        while _stream_running:
            schedule.run_pending()
            time.sleep(30)  # 每30秒检查一次调度

        print("[Stream] 流式更新已停止")

    _stream_thread = threading.Thread(target=_run, daemon=True)
    _stream_thread.start()
    print(f"[Stream] 后台线程已启动（间隔 {interval_minutes} 分钟）")


def stop_stream():
    """停止流式更新"""
    global _stream_running
    _stream_running = False
    print("[Stream] 正在停止流式更新...")


# ── 功能三：过期删除 ──────────────────────────────────────────────────

def delete_expired(expire_days: int = NEWS_EXPIRE_DAYS):
    """
    删除超过 expire_days 天的旧新闻
    保持数据库干净，避免旧新闻干扰检索

    Args:
        expire_days: 保留天数，默认30天
    """
    collection = _get_news_collection()
    cutoff_date = (datetime.now() - timedelta(days=expire_days)).strftime("%Y-%m-%d")

    print(f"[Cleanup] 删除 {cutoff_date} 之前的新闻...")

    try:
        # ChromaDB 按元数据条件删除
        collection.delete(
            where={
                "date": {"$lt": cutoff_date}
            }
        )
        print(f"[Cleanup] 删除完成，当前剩余 {collection.count()} 条新闻")

    except Exception as e:
        print(f"[Cleanup] 删除失败: {e}")


def schedule_daily_cleanup(hour: int = 2, expire_days: int = NEWS_EXPIRE_DAYS):
    """
    每天凌晨 hour 点自动清理过期新闻
    通常配合 start_stream 一起使用
    """
    schedule.every().day.at(f"{hour:02d}:00").do(delete_expired, expire_days=expire_days)
    print(f"[Cleanup] 已设置每天 {hour:02d}:00 自动清理 {expire_days} 天前的新闻")


# ── 检索接口 ──────────────────────────────────────────────────────────

def retrieve_news(
    query: str,
    stock_code: str = None,
    k: int = 10,
    days: int = 7,
) -> str:
    """
    从新闻库检索相关新闻

    Args:
        query: 检索关键词（如"净利润""订单""政策"）
        stock_code: 指定股票代码，None则全库检索
        k: 返回条数
        days: 只看最近N天的新闻，默认7天
    """
    collection = _get_news_collection()

    if collection.count() == 0:
        return "新闻库为空，请先运行 bulk_index() 初始化"

    try:
        # 构建过滤条件
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
            stock_name = meta.get("stock_name", "")
            pub_time = meta.get("pub_time", "")
            output.append(f"【{stock_name} | {pub_time}】{meta.get('title', doc)}")

        return "\n".join(output)

    except Exception as e:
        print(f"[NewsIndexer] 检索失败: {e}")
        return ""


def get_stats() -> dict:
    """获取新闻库统计信息"""
    collection = _get_news_collection()
    total = collection.count()

    return {
        "total_news": total,
        "collection": NEWS_COLLECTION,
        "expire_days": NEWS_EXPIRE_DAYS,
        "watch_stocks": len(WATCH_LIST),
        "stream_running": _stream_running,
    }


# ── 快速启动 ──────────────────────────────────────────────────────────

def start_news_system(
    bulk_first: bool = True,
    stream_interval: int = STREAM_INTERVAL_MINUTES,
    cleanup_hour: int = 2,
):
    """
    一键启动新闻系统：
    1. 批量入库（如果库是空的）
    2. 启动流式更新
    3. 设置每日清理
    """
    collection = _get_news_collection()

    # 库是空的才批量入库
    if bulk_first and collection.count() == 0:
        print("[NewsSystem] 新闻库为空，开始批量初始化...")
        bulk_index()
    else:
        print(f"[NewsSystem] 新闻库已有 {collection.count()} 条，跳过批量入库")

    # 启动流式更新
    start_stream(interval_minutes=stream_interval)

    # 设置每日清理
    schedule_daily_cleanup(hour=cleanup_hour)

    stats = get_stats()
    print(f"[NewsSystem] 启动完成：{stats}")