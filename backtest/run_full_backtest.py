import sys
import os

sys.path.insert(0, r"D:\code\ProjectExample\Neon_stock_trading_agent")

from dotenv import load_dotenv

load_dotenv(r"D:\code\ProjectExample\Neon_stock_trading_agent\.env", override=True)

from backtest.stock_universe import STOCK_UNIVERSE
from backtest.fundamental_filter import get_fundamental_data, score_stock
from backtest.data_loader import get_stock_data_tushare
from backtest.engine import run_backtest, format_result
from backtest.optimizer import grid_search, format_optimization_result

token = os.getenv("TUSHARE_TOKEN")

# 收集所有评分>=65的股票
qualified = {}
for sector, stocks in STOCK_UNIVERSE.items():
    for code, name in stocks.items():
        if code in qualified:
            continue
        data = get_fundamental_data(code)
        price = data.get("price") or 0
        market_cap = data.get("market_cap") or 0
        score = score_stock(data)

        if score < 65:
            continue
        if price <= 0 or price > 100:
            print(f"  {name}({code}) 跳过：股价{price:.1f}元")
            continue
        if market_cap < 5_000_000_000:
            print(f"  {name}({code}) 跳过：市值{market_cap/1e8:.0f}亿偏小")
            continue
        qualified[code] = {"name": name, "sector": sector, "score": score}

print(f"共{len(qualified)}只股票通过筛选，开始回测...")

# 回测
results = []
stock_dfs = {}
for code, info in qualified.items():
    try:
        df = get_stock_data_tushare(code, "20240901", "20260530", token)
        if len(df) < 60:
            continue
        stock_dfs[code] = df
        result = run_backtest(df, strategy_name="kdj_oversold", printlog=False)
        results.append(
            {
                "code": code,
                "name": info["name"],
                "sector": info["sector"],
                "score": info["score"],
                "total_return": result["total_return"],
                "sharpe": result["sharpe"],
                "max_drawdown": result["max_drawdown"],
                "trade_count": result["trade_count"],
                "win_rate": result["win_rate"],
            }
        )
        print(
            f"{info['name']}({code}): 收益={result['total_return']:+.1f}%"
            f" 夏普={result['sharpe']} 交易={result['trade_count']}次"
        )
    except Exception as e:
        print(f"{info['name']}({code}) 失败: {e}")

# 排序
results = [r for r in results if r["sharpe"] is not None]
results.sort(key=lambda x: x["sharpe"], reverse=True)

print("\n===== 回测结果排名（按夏普比率）=====")
for i, r in enumerate(results[:10], 1):
    print(
        f"Top{i}: {r['name']}({r['code']}) [{r['sector']}]"
        f" 收益={r['total_return']:+.1f}%"
        f" 夏普={r['sharpe']}"
        f" 回撤={r['max_drawdown']:.1f}%"
        f" 交易={r['trade_count']}次"
        f" 胜率={r['win_rate']}%"
    )

# 对Top10做参数优化
print("\n===== Top10参数优化 =====")
for r in results[:10]:
    code = r["code"]
    name = r["name"]
    if code not in stock_dfs:
        continue
    print(f"\n--- {name}({code}) ---")
    opt_results = grid_search(stock_dfs[code], "kdj_oversold", top_n=3)
    print(format_optimization_result(opt_results, "kdj_oversold"))
