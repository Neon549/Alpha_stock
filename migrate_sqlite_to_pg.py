#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@author: yulin
@created: 2026/7/21 11:17
@updated: 2026/7/21 11:17
@version: 1.0
@description:
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
migrate_sqlite_to_pg.py
一次性迁移脚本：把旧 SQLite 数据导入 PostgreSQL

运行一次即可，之后删掉此脚本。
"""

import sqlite3
from pathlib import Path
from db import execute, init_db

USERS_DB = Path("/home/ubuntu/Alpha_stock/users.db")
MEMORY_DB = Path("memory/trading_memory.db")
CONV_DB = Path("/home/ubuntu/Alpha_stock/conversations.db")


def migrate_users():
    if not USERS_DB.exists():
        print("⚠️  users.db 不存在，跳过")
        return
    conn = sqlite3.connect(USERS_DB)
    cur = conn.cursor()
    cur.execute("SELECT username, password_hash, salt, created_at FROM users")
    rows = cur.fetchall()
    conn.close()

    for username, pw_hash, salt, created_at in rows:
        try:
            execute(
                """
                INSERT INTO users (username, password_hash, salt, created_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (username) DO NOTHING
                """,
                (username, pw_hash, salt or "", created_at),
            )
        except Exception as e:
            print(f"  ⚠️ 用户 {username} 迁移失败: {e}")

    print(f"✅ users 迁移完成：{len(rows)} 条")


def migrate_memory():
    if not MEMORY_DB.exists():
        print("⚠️  trading_memory.db 不存在，跳过")
        return
    conn = sqlite3.connect(MEMORY_DB)
    cur = conn.cursor()

    # trading_decisions
    try:
        cur.execute(
            "SELECT stock_code, analysis_date, decision, fundamental_summary, technical_summary, sentiment_summary, created_at FROM trading_decisions"
        )
        for row in cur.fetchall():
            execute(
                """
                INSERT INTO trading_decisions
                    (stock_code, analysis_date, decision, fundamental_summary, technical_summary, sentiment_summary, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                row,
            )
        print("✅ trading_decisions 迁移完成")
    except Exception as e:
        print(f"⚠️ trading_decisions 迁移失败: {e}")

    # analysis_reflections
    try:
        cur.execute(
            "SELECT stock_code, reflection, created_at FROM analysis_reflections"
        )
        for row in cur.fetchall():
            execute(
                "INSERT INTO analysis_reflections (stock_code, reflection, created_at) VALUES (%s, %s, %s)",
                row,
            )
        print("✅ analysis_reflections 迁移完成")
    except Exception as e:
        print(f"⚠️ analysis_reflections 迁移失败: {e}")

    # backtest_results
    try:
        cur.execute(
            "SELECT stock_code, strategy, result_summary, created_at FROM backtest_results"
        )
        for row in cur.fetchall():
            execute(
                "INSERT INTO backtest_results (stock_code, strategy, result_summary, created_at) VALUES (%s, %s, %s, %s)",
                row,
            )
        print("✅ backtest_results 迁移完成")
    except Exception as e:
        print(f"⚠️ backtest_results 迁移失败: {e}")

    conn.close()


if __name__ == "__main__":
    print("🚀 开始迁移 SQLite → PostgreSQL")
    init_db()
    migrate_users()
    migrate_memory()
    print("🎉 迁移完成")
