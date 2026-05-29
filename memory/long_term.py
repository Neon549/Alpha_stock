# memory/long_term.py
# ============ 改动说明 ============
# 新增: backtest_results 表
# 新增: save_backtest_result() / get_backtest_history() 方法
# 原有 trading_decisions / analysis_reflections 表不变
# ==================================

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("memory/trading_memory.db")


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 原有表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trading_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            analysis_date TEXT NOT NULL,
            decision TEXT NOT NULL,
            fundamental_summary TEXT,
            technical_summary TEXT,
            sentiment_summary TEXT,
            target_price REAL,
            stop_loss REAL,
            actual_result TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_reflections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            reflection TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # ── 新增：回测结果表 ──────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            strategy TEXT NOT NULL,
            result_summary TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    print("✅ 数据库初始化完成")


class LongTermMemory:

    def __init__(self):
        init_db()

    # ── 原有方法（不变） ────────────────────────

    def save_decision(
        self,
        stock_code: str,
        decision: str,
        fundamental_summary: str = "",
        technical_summary: str = "",
        sentiment_summary: str = "",
    ):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO trading_decisions
            (stock_code, analysis_date, decision, fundamental_summary,
             technical_summary, sentiment_summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            stock_code,
            datetime.now().strftime("%Y-%m-%d"),
            decision[:500],
            fundamental_summary[:300],
            technical_summary[:300],
            sentiment_summary[:300],
            datetime.now().isoformat(),
        ))
        conn.commit()
        conn.close()
        print(f"💾 决策已保存到长期记忆")

    def get_history(self, stock_code: str, limit: int = 3) -> str:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT analysis_date, decision, created_at
            FROM trading_decisions
            WHERE stock_code = ?
            ORDER BY created_at DESC LIMIT ?
        """, (stock_code, limit))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return f"暂无 {stock_code} 的历史分析记录"

        history = [f"## {stock_code} 历史决策记录"]
        for date, decision, created_at in rows:
            history.append(f"\n### {date}\n{decision[:200]}...")
        return "\n".join(history)

    def save_reflection(self, stock_code: str, reflection: str):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO analysis_reflections (stock_code, reflection, created_at)
            VALUES (?, ?, ?)
        """, (stock_code, reflection, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def get_reflections(self, stock_code: str) -> str:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT reflection, created_at
            FROM analysis_reflections
            WHERE stock_code = ?
            ORDER BY created_at DESC LIMIT 3
        """, (stock_code,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "暂无复盘记录"
        return "\n\n".join([f"[{r[1][:10]}] {r[0]}" for r in rows])

    # ── 新增：回测结果存储/检索 ─────────────────

    def save_backtest_result(
        self,
        stock_code: str,
        strategy: str,
        result_summary: str,
    ):
        """保存回测结果到长期记忆"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO backtest_results
            (stock_code, strategy, result_summary, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            stock_code,
            strategy,
            result_summary[:500],
            datetime.now().isoformat(),
        ))
        conn.commit()
        conn.close()
        print(f"💾 回测结果已保存: {stock_code} - {strategy}")

    def get_backtest_history(self, stock_code: str, limit: int = 5) -> str:
        """获取某只股票的历史回测记录"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT strategy, result_summary, created_at
            FROM backtest_results
            WHERE stock_code = ?
            ORDER BY created_at DESC LIMIT ?
        """, (stock_code, limit))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return f"暂无 {stock_code} 的回测记录"

        history = [f"## {stock_code} 历史回测记录"]
        for strategy, summary, created_at in rows:
            history.append(f"\n### {created_at[:10]} - {strategy}\n{summary}")
        return "\n".join(history)