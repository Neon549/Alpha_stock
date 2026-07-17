import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router
import sys

sys.stdout.reconfigure(encoding="utf-8")
app = FastAPI(
    title="AlphaStock · 智能投研助手",
    description="分析基本面、技术面、情绪面，结合Alpha因子回测，辅助A股交易决策",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.on_event("startup")
async def startup_event():
    """
    服务启动时自动启动新闻系统：
    1. 新闻库为空时批量初始化（18只股票 × 50条）
    2. 每5分钟流式更新新增新闻
    3. 每天凌晨2点清理30天前的旧新闻
    """
    try:
        from rag.news_indexer import start_news_system
        start_news_system(
            bulk_first=True,          # 库为空时批量入库
            stream_interval=5,        # 每5分钟更新一次
            cleanup_hour=2,           # 每天凌晨2点清理
        )
    except Exception as e:
        print(f"[Startup] 新闻系统启动失败（不影响主服务）: {e}")


@app.get("/")
def root():
    return {
        "message": "AlphaStock · 智能投研助手",
        "docs": "/docs",
        "version": "1.0.0"
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/news/stats")
def news_stats():
    """查看新闻库统计信息"""
    try:
        from rag.news_indexer import get_stats
        return get_stats()
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )