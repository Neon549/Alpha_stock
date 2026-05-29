# api/routes.py
# ============ 改动说明 ============
# 新增: POST /api/v1/backtest 回测接口
# 新增: BacktestRequest / BacktestResponse 模型
# 原有接口不变
# ==================================

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from graph.trading_graph import run_trading_analysis
from memory.long_term import LongTermMemory

router = APIRouter()
memory = LongTermMemory()


# ── 原有模型 ────────────────────────────────

class AnalyzeRequest(BaseModel):
    stock_code: str
    force_refresh: bool = False

class AnalyzeResponse(BaseModel):
    stock_code: str
    decision: str
    fundamental_report: str
    technical_report: str
    sentiment_report: str
    researcher_analysis: str
    status: str = "success"

class HistoryResponse(BaseModel):
    stock_code: str
    history: str


# ── 新增：回测模型 ──────────────────────────

class BacktestRequest(BaseModel):
    stock_code: str
    strategy: str = "kdj_macd"          # kdj_macd / rsi / boll
    start_date: str = "20220101"
    end_date: str = "20261231"
    initial_cash: float = 100000.0

class BacktestResponse(BaseModel):
    stock_code: str
    strategy: str
    total_return: float
    sharpe: Optional[float]
    max_drawdown: float
    trade_count: int
    win_rate: float
    report_text: str
    status: str = "success"


# ── 原有接口 ────────────────────────────────

@router.get("/health")
def health_check():
    return {"status": "ok", "message": "Trading Agent System is running"}


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_stock(request: AnalyzeRequest):
    try:
        stock_code = request.stock_code.strip()
        if not stock_code:
            raise HTTPException(status_code=400, detail="股票代码不能为空")

        print(f"📨 收到分析请求：{stock_code}")
        result = run_trading_analysis(stock_code)

        return AnalyzeResponse(
            stock_code=stock_code,
            decision=result.get("final_decision", ""),
            fundamental_report=result.get("fundamental_report", ""),
            technical_report=result.get("technical_report", ""),
            sentiment_report=result.get("sentiment_report", ""),
            researcher_analysis=result.get("bull_argument", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败：{str(e)}")


@router.get("/history/{stock_code}", response_model=HistoryResponse)
def get_history(stock_code: str):
    history = memory.get_history(stock_code)
    return HistoryResponse(stock_code=stock_code, history=history)


@router.get("/stocks/info/{stock_code}")
def get_stock_info(stock_code: str):
    try:
        from tools.akshare_tools import get_stock_price
        result = get_stock_price.invoke({"symbol": stock_code})
        return {"stock_code": stock_code, "info": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 新增：回测接口 ──────────────────────────

@router.post("/backtest", response_model=BacktestResponse)
def run_backtest_api(request: BacktestRequest):
    """
    独立回测接口 —— 不走完整的 Multi-Agent 分析流程
    直接执行策略回测，返回绩效指标
    """
    try:
        import os
        from backtest.data_loader import get_stock_data_tushare, get_mock_data
        from backtest.engine import run_backtest, format_result

        stock_code = request.stock_code.strip()
        if not stock_code:
            raise HTTPException(status_code=400, detail="股票代码不能为空")

        # 获取数据
        token = os.getenv("TUSHARE_TOKEN", "")
        if token:
            df = get_stock_data_tushare(
                stock_code, request.start_date, request.end_date, token
            )
        else:
            df = get_mock_data(stock_code, days=500)

        if df.empty or len(df) < 60:
            raise HTTPException(status_code=400, detail=f"数据不足(仅{len(df)}根K线)")

        # 执行回测
        result = run_backtest(
            df=df,
            strategy_name=request.strategy,
            initial_cash=request.initial_cash,
        )

        report_text = format_result(result)

        # 存入记忆（复用现有 long_term memory）
        memory.save_backtest_result(
            stock_code=stock_code,
            strategy=request.strategy,
            result_summary=report_text[:500],
        )

        return BacktestResponse(
            stock_code=stock_code,
            strategy=request.strategy,
            total_return=result["total_return"],
            sharpe=result["sharpe"],
            max_drawdown=result["max_drawdown"],
            trade_count=result["trade_count"],
            win_rate=result["win_rate"],
            report_text=report_text,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回测失败：{str(e)}")


@router.get("/backtest/strategies")
def list_strategies():
    """列出所有可用的回测策略"""
    from backtest.strategies import STRATEGY_MAP
    return {
        "strategies": [
            {"name": "kdj_macd", "description": "KDJ金叉 + MACD确认（双重信号过滤）"},
            {"name": "rsi",      "description": "RSI超卖买入 / 超买卖出"},
            {"name": "boll",     "description": "布林带下轨买入 / 上轨卖出"},
        ]
    }


@router.get("/backtest/history/{stock_code}")
def get_backtest_history(stock_code: str):
    """获取某只股票的历史回测记录"""
    history = memory.get_backtest_history(stock_code)
    return {"stock_code": stock_code, "history": history}