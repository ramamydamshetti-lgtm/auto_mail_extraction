import os
import time
from dotenv import load_dotenv
import openai

load_dotenv()
client = openai.OpenAI(
    api_key=os.environ.get("GEMINI_API_KEY"),
    base_url=os.environ.get("GEMINI_BASE_URL"),
)

for m in [
    "models/gemini-3.5-flash-lite",
    "models/gemini-2.5-flash-lite",
    "models/gemini-3.6-flash",
    "models/gemini-flash-lite-latest",
]:
    try:
        resp = client.chat.completions.create(
            model=m,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": 'Return {"label": "NOT_A_REQUIREMENT", "confidence": 0.9}'}],
        )
        print(f"Model {m} SUCCESS: {resp.choices[0].message.content!r}")
    except Exception as e:
        print(f"Model {m} FAILED: {type(e).__name__}: {e}")
