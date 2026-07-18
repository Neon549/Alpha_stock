#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@author: yulin
@created: 2026/7/18 12:23
@updated: 2026/7/18 12:23
@version: 1.0
@description:
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
api/auth.py
用户注册/登录模块

存储：SQLite（users.db）
密码：SHA256 + salt 哈希，不存明文
Token：简单的 UUID token，登录后返回
"""

import sqlite3
import hashlib
import uuid
import os
import threading
from datetime import datetime
from pathlib import Path

DB_PATH = "users.db"
_lock = threading.Lock()


def _get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn


def init_db():
    """初始化用户表"""
    with _lock:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()


def _hash_password(password: str, salt: str) -> str:
    """SHA256 + salt 哈希"""
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


def register(username: str, password: str) -> dict:
    """
    注册新用户
    返回：{success: bool, message: str, token: str}
    """
    username = (username or "").strip()
    password = (password or "").strip()

    if len(username) < 2:
        return {"success": False, "message": "用户名至少2个字符"}
    if len(password) < 4:
        return {"success": False, "message": "密码至少4个字符"}

    with _lock:
        conn = _get_conn()
        cur = conn.cursor()

        # 检查用户名是否已存在
        cur.execute("SELECT username FROM users WHERE username = ?", (username,))
        if cur.fetchone():
            conn.close()
            return {"success": False, "message": "用户名已存在"}

        # 创建用户
        salt = uuid.uuid4().hex
        password_hash = _hash_password(password, salt)
        now = datetime.now().isoformat()

        cur.execute(
            "INSERT INTO users (username, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
            (username, password_hash, salt, now),
        )

        # 生成token
        token = uuid.uuid4().hex
        cur.execute(
            "INSERT INTO tokens (token, username, created_at) VALUES (?, ?, ?)",
            (token, username, now),
        )

        conn.commit()
        conn.close()

    return {
        "success": True,
        "message": "注册成功",
        "token": token,
        "username": username,
    }


def login(username: str, password: str) -> dict:
    """
    用户登录
    返回：{success: bool, message: str, token: str}
    """
    username = (username or "").strip()
    password = (password or "").strip()

    with _lock:
        conn = _get_conn()
        cur = conn.cursor()

        cur.execute(
            "SELECT password_hash, salt FROM users WHERE username = ?", (username,)
        )
        row = cur.fetchone()

        if not row:
            conn.close()
            return {"success": False, "message": "用户名不存在"}

        password_hash, salt = row
        if _hash_password(password, salt) != password_hash:
            conn.close()
            return {"success": False, "message": "密码错误"}

        # 生成新token
        token = uuid.uuid4().hex
        now = datetime.now().isoformat()
        cur.execute(
            "INSERT INTO tokens (token, username, created_at) VALUES (?, ?, ?)",
            (token, username, now),
        )
        conn.commit()
        conn.close()

    return {
        "success": True,
        "message": "登录成功",
        "token": token,
        "username": username,
    }


def verify_token(token: str) -> dict:
    """
    验证token有效性
    返回：{valid: bool, username: str}
    """
    if not token:
        return {"valid": False, "username": ""}

    with _lock:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT username FROM tokens WHERE token = ?", (token,))
        row = cur.fetchone()
        conn.close()

    if row:
        return {"valid": True, "username": row[0]}
    return {"valid": False, "username": ""}


def logout(token: str) -> dict:
    """登出，删除token"""
    with _lock:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM tokens WHERE token = ?", (token,))
        conn.commit()
        conn.close()
    return {"success": True, "message": "已登出"}


# 初始化数据库
init_db()
