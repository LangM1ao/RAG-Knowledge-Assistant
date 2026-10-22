from openai import OpenAI

from app.core.config import LLM_MODEL, OPENAI_API_KEY

def generate_answer(messages: list[dict]) -> str:
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured.")

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
    )
    return response.choices[0].message.content


def generate_structured_answer(messages: list[dict], response_format):
    """复用现有模型配置，通过 SDK 返回经过结构解析的校验对象。"""
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured.")

    # 校验请求最多等待 30 秒，不额外自动重试，避免长时间阻塞问答。
    client = OpenAI(api_key=OPENAI_API_KEY, timeout=30.0, max_retries=0)
    response = client.chat.completions.parse(
        model=LLM_MODEL,
        messages=messages,
        response_format=response_format,
    )
    message = response.choices[0].message
    if message.refusal or message.parsed is None:
        raise ValueError("Verification did not return a structured result")
    return message.parsed
