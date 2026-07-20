#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@author: yulin
@created: 2026/6/1 18:06
@updated: 2026/6/1 18:06
@version: 1.0
@description:
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 每日增量更新脚本
# 每天15:35自动运行，增量更新所有股票数据并推送到git

import os
import time
import subprocess
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)


def daily_update():
    # 周末跳过
    if datetime.now().weekday() >= 5:
        print("今天是周末，跳过更新")
        return

    # 未收盘跳过
    now = datetime.now()

    from backtest.stock_universe import ALL_STOCKS
    from backtest.data_loader import get_stock_data_incremental

    token = os.getenv("TUSHARE_TOKEN", "")
    stocks = {code: info["name"] for code, info in ALL_STOCKS.items()}
    total = len(stocks)

    print(f"\n{'='*50}")
    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 开始每日增量更新 {total}只股票"
    )

    success = 0
    failed = 0

    for i, (code, name) in enumerate(stocks.items()):
        print(f"[{i+1}/{total}] {name}({code})", end=" ")
        try:
            df = get_stock_data_incremental(code, token=token)
            print(f"✅ {len(df)}根")
            success += 1
        except Exception as e:
            if "频率超限" in str(e):
                print(f"⚠️ 限速，等60秒...")
                time.sleep(60)
                try:
                    df = get_stock_data_incremental(code, token=token)
                    print(f"✅ 重试成功 {len(df)}根")
                    success += 1
                except Exception as e2:
                    print(f"❌ 重试失败: {e2}")
                    failed += 1
            else:
                print(f"❌ {e}")
                failed += 1
        time.sleep(1.5)

    print(f"\n✅ 更新完成: 成功{success}只 失败{failed}只")
    print("开始推送git...")

    project_dir = Path(__file__).parent.parent
    subprocess.run(["git", "add", "backtest/data_cache/"], cwd=project_dir)
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            f"data: {datetime.now().strftime('%Y-%m-%d')}每日增量更新",
        ],
        cwd=project_dir,
    )
    subprocess.run(["git", "push", "origin", "main"], cwd=project_dir)
    subprocess.run(["git", "push", "github", "main"], cwd=project_dir)
    print("✅ 推送完成")


if __name__ == "__main__":
    daily_update()
