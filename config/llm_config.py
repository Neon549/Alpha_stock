from pathlib import Path
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not API_KEY:
    raise ValueError("DEEPSEEK_API_KEY 未设置")


def get_llm(model: str = "deepseek-chat", temperature: float = 0.1):
    return ChatOpenAI(
        model=model,
        api_key=API_KEY,
        base_url="https://api.deepseek.com",
        temperature=temperature,
    )


deep_llm = get_llm("deepseek-chat")
quick_llm = get_llm("deepseek-chat")


# TechLens本地推理backend（替换technical_analyst的DeepSeek调用）
import requests as _requests

class TechLensClient:
    def __init__(self, base_url="http://localhost:8088"):
        self.base_url = base_url

    def analyze(self, stock_code, history_result, price_result, kdj_result):
        resp = _requests.post(f"{self.base_url}/analyze", json={
            "stock_code": stock_code,
            "history_result": history_result,
            "price_result": price_result,
            "kdj_result": kdj_result,
        }, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def is_available(self):
        try:
            r = _requests.get(f"{self.base_url}/health", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

techlens_client = TechLensClient()
