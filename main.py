import os
import sys
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/")
def root():
    return {"message": "AlphaStock · 智能投研助手", "docs": "/docs", "version": "2.0.0"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.on_event("startup")
async def startup_event():
    """延迟加载路由 + 后台初始化新闻系统，避免阻塞端口绑定"""
    import threading

    def _heavy_init():
        try:
            # 1. 延迟加载业务路由（包含langchain/langgraph等重依赖）
            from api.routes import router

            app.include_router(router, prefix="/api/v1")
            print("[Startup] 业务路由加载完成 ✅")

            # 2. 新闻系统
            from rag.news_indexer import start_news_system

            start_news_system(bulk_first=True, stream_interval=5, cleanup_hour=2)
            print("[Startup] 新闻系统启动完成 ✅")
        except Exception as e:
            print(f"[Startup] 后台初始化失败: {e}")
            import traceback

            traceback.print_exc()

    threading.Thread(target=_heavy_init, daemon=True).start()
    print("[Startup] FastAPI已就绪（端口已绑定），业务模块后台加载中...")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
