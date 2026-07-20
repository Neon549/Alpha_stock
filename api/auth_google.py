"""
api/auth_google.py  ──  Google OAuth 2.0 登录
"""
import os
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from urllib.parse import urlencode

router = APIRouter()

CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "https://alphastock.cloud/api/v1/auth/google/callback")
FRONTEND_URL  = "https://alphastock.cloud"

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

    # 用 code 换 token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            }
        )
    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return RedirectResponse(f"{FRONTEND_URL}?login_error=token_failed")

    # 获取用户信息
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
    user_info = user_resp.json()
    email    = user_info.get("email", "")
    name     = user_info.get("name", email.split("@")[0])
    google_id = user_info.get("id", "")

    # 用 email 作为用户名，在本地数据库注册或登录
    import sqlite3, hashlib, secrets
    db_path = "/home/ubuntu/Alpha_stock/users.db"
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    # 确保 users 表有 google_id 字段
    try:
        cur.execute("ALTER TABLE users ADD COLUMN google_id TEXT")
        conn.commit()
    except:
        pass

    # 查找已有账号
    cur.execute("SELECT username, token FROM users WHERE google_id=? OR username=?", (google_id, email))
    row = cur.fetchone()

    if row:
        username = row[0]
        # 刷新 token
        new_token = secrets.token_hex(16)
        cur.execute("UPDATE users SET token=? WHERE username=?", (new_token, username))
        conn.commit()
        token = new_token
    else:
        # 新用户注册
        username  = email
        new_token = secrets.token_hex(16)
        password_hash = hashlib.sha256(secrets.token_hex(32).encode()).hexdigest()
        try:
            cur.execute(
                "INSERT INTO users (username, password_hash, token, google_id) VALUES (?,?,?,?)",
                (username, password_hash, new_token, google_id)
            )
            conn.commit()
        except Exception as e:
            conn.close()
            return RedirectResponse(f"{FRONTEND_URL}?login_error=db_error")
        token = new_token

    conn.close()

    # 跳回落地页，带上 token
    params = urlencode({
        "google_login": "success",
        "token": token,
        "username": name or username,
    })
    return RedirectResponse(f"{FRONTEND_URL}?{params}")

from pydantic import BaseModel

class GoogleTokenRequest(BaseModel):
    id_token: str

class GoogleTokenRequest2(BaseModel):
    id_token: str
    email: str = ""
    name: str = ""
    google_id: str = ""

@router.post("/auth/google/token")
async def google_token_login(request: GoogleTokenRequest2):
    """接收前端解析的 Google 用户信息，直接注册/登录"""
    email     = request.email
    name      = request.name or (email.split("@")[0] if email else "Google用户")
    google_id = request.google_id
    if not email and not google_id:
        raise HTTPException(400, detail="缺少用户信息")

    import sqlite3, hashlib, secrets
    db_path = "/home/ubuntu/Alpha_stock/users.db"
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()
    try:
        cur.execute("ALTER TABLE users ADD COLUMN google_id TEXT")
        conn.commit()
    except: pass

    cur.execute("SELECT username FROM users WHERE google_id=? OR username=?", (google_id, email))
    row = cur.fetchone()
    new_token = secrets.token_hex(16)
    if row:
        username = row[0]
        cur.execute("UPDATE users SET token=? WHERE username=?", (new_token, username))
    else:
        username = email
        pw_hash  = hashlib.sha256(secrets.token_hex(32).encode()).hexdigest()
        try:
            cur.execute("INSERT INTO users (username, password_hash, token, google_id) VALUES (?,?,?,?)",
                        (username, pw_hash, new_token, google_id))
        except:
            cur.execute("UPDATE users SET token=? WHERE username=?", (new_token, username))
    conn.commit()
    conn.close()
    return {"token": new_token, "username": username, "display_name": name or username.split('@')[0]}
