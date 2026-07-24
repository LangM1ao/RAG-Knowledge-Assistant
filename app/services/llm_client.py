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
