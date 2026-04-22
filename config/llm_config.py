from pathlib import Path
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

env_path = Path(__file__).resolve().parent.parent / ".env"
print(f"Loading env from: {env_path}")

load_dotenv(dotenv_path=env_path, override=True)

API_KEY = os.getenv("DASHSCOPE_API_KEY")
if not API_KEY:
    raise ValueError("DASHSCOPE_API_KEY 未设置")

def get_llm(model: str = "qwen-plus", temperature: float = 0.1):
    return ChatOpenAI(
        model=model,
        api_key=API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=temperature,
    )

deep_llm = get_llm("qwen-plus")
quick_llm = get_llm("qwen-turbo")