# ================================================================
# PostgreSQL + pgvector 迁移指南
# ================================================================

# ── 1. 安装依赖 ──────────────────────────────────────────────────
pip install psycopg2-binary pgvector sentence-transformers

# ── 2. 服务器上安装 PostgreSQL + pgvector ────────────────────────
# Ubuntu 22.04:
sudo apt update
sudo apt install -y postgresql postgresql-contrib

# 安装 pgvector 扩展：
sudo apt install -y postgresql-15-pgvector
# 或者编译安装：
# cd /tmp && git clone https://github.com/pgvector/pgvector.git
# cd pgvector && make && sudo make install

# ── 3. 创建数据库和用户 ──────────────────────────────────────────
sudo -u postgres psql << 'EOF'
CREATE USER alphastock WITH PASSWORD 'your_strong_password';
CREATE DATABASE alphastock OWNER alphastock;
GRANT ALL PRIVILEGES ON DATABASE alphastock TO alphastock;
EOF

# ── 4. .env 新增以下配置 ─────────────────────────────────────────
POSTGRES_DSN=postgresql://alphastock:your_strong_password@localhost:5432/alphastock

# ── 5. 替换文件 ──────────────────────────────────────────────────
# db.py              → 项目根目录（新文件）
# api/auth.py        → 替换原文件
# api/auth_google.py → 替换原文件（同步替换 backtest/api/ 下的副本）
# memory/long_term.py→ 替换原文件
# rag/news_indexer.py→ 替换原文件

# ── 6. main.py 启动时初始化 ──────────────────────────────────────
# 在 main.py 顶部加两行：
# from db import init_db
# init_db()   # 幂等，重复执行无害

# ── 7. 验证 ──────────────────────────────────────────────────────
python db.py   # 应输出：✅ 数据库表初始化完成（PostgreSQL + pgvector）

# ── 8. 迁移旧数据（可选）────────────────────────────────────────
# 如果 users.db 里有历史用户数据，运行迁移脚本：
python migrate_sqlite_to_pg.py