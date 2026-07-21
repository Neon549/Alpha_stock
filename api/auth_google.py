#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api/auth_google.py  ──  Google OAuth 2.0 登录（PostgreSQL 版）
"""

import os
import secrets
import hashlib
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from urllib.parse import urlencode
from pydantic import BaseModel

from db import execute

router = APIRouter()

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI", "https://alphastock.cloud/api/v1/auth/google/callback"
)
FRONTEND_URL = "https://alphastock.cloud"


# ── 内部：查找或创建 Google 用户 ──────────────────────────────────────


def _upsert_google_user(email: str, name: str, google_id: str) -> str:
    """
    查找已有账号（by google_id 或 email）→ 更新 token
    找不到 → 新建用户
    返回 new_token
    """
    new_token = secrets.token_hex(16)

    row = execute(
        "SELECT username FROM users WHERE google_id = %s OR username = %s",
        (google_id, email),
        fetch="one",
    )

    if row:
        username = row[0]
        execute(
            "UPDATE users SET token = %s WHERE username = %s",
            (new_token, username),
        )
    else:
        username = email
        pw_hash = hashlib.sha256(secrets.token_hex(32).encode()).hexdigest()
        execute(
            """
            INSERT INTO users (username, password_hash, salt, google_id, token)
            VALUES (%s, %s, '', %s, %s)
            ON CONFLICT (username) DO UPDATE SET token = EXCLUDED.token
            """,
            (username, pw_hash, google_id, new_token),
        )

    # 同步写入 tokens 表（供 verify_token 使用）
    execute(
        """
        INSERT INTO tokens (token, username) VALUES (%s, %s)
        ON CONFLICT (token) DO NOTHING
        """,
        (new_token, username),
    )

    return new_token


# ── OAuth 重定向流程 ───────────────────────────────────────────────────


@router.get("/auth/google")
def google_login():
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(url)


@router.get("/auth/google/callback")
async def google_callback(code: str = None, error: str = None):
    if error:
        return RedirectResponse(f"{FRONTEND_URL}?login_error={error}")
    if not code:
        return RedirectResponse(f"{FRONTEND_URL}?login_error=no_code")

    # code → access_token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return RedirectResponse(f"{FRONTEND_URL}?login_error=token_failed")

    # access_token → 用户信息
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    user_info = user_resp.json()
    email = user_info.get("email", "")
    name = user_info.get("name", email.split("@")[0])
    google_id = user_info.get("id", "")

    token = _upsert_google_user(email, name, google_id)

    params = urlencode(
        {
            "google_login": "success",
            "token": token,
            "username": name or email.split("@")[0],
        }
    )
    return RedirectResponse(f"{FRONTEND_URL}?{params}")


# ── 前端直接传 Google 用户信息（One Tap 流程）────────────────────────


class GoogleTokenRequest2(BaseModel):
    id_token: str = ""
    email: str = ""
    name: str = ""
    google_id: str = ""


@router.post("/auth/google/token")
async def google_token_login(request: GoogleTokenRequest2):
    """接收前端解析的 Google 用户信息，直接注册/登录"""
    email = request.email
    name = request.name or (email.split("@")[0] if email else "Google用户")
    google_id = request.google_id

    if not email and not google_id:
        raise HTTPException(400, detail="缺少用户信息")

    token = _upsert_google_user(email, name, google_id)
    username = email

    return {
        "token": token,
        "username": username,
        "display_name": name or username.split("@")[0],
    }
