import os
from typing import List, Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="AURA AI API", version="0.2.0")

allowed = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in allowed],
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)


class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=6000)


class ChatRequest(BaseModel):
    messages: List[Message] = Field(min_length=1, max_length=40)
    web_search: bool = False


@app.get("/health")
async def health():
    return {"status": "ok", "service": "AURA AI"}


async def search_web(query: str):
    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="کلید جست‌وجوی Tavily تنظیم نشده است."
        )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": 5,
                    "include_answer": False
                }
            )

        response.raise_for_status()
        data = response.json()

        return data.get("results", [])

    except httpx.HTTPError:
        raise HTTPException(
            status_code=502,
            detail="جست‌وجوی اینترنتی ناموفق بود."
        )


@app.post("/api/chat")
async def chat(payload: ChatRequest):
    api_key = os.getenv("AI_API_KEY")

    api_url = os.getenv(
        "AI_API_URL",
        "https://api.openai.com/v1/chat/completions"
    )

    model = os.getenv("AI_MODEL", "gpt-4o-mini")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="کلید هوش مصنوعی روی سرور تنظیم نشده است."
        )

    messages = [
        m.model_dump()
        for m in payload.messages
    ]

    sources = []

    if payload.web_search:
        last_user_message = next(
            (
                m.content
                for m in reversed(payload.messages)
                if m.role == "user"
            ),
            ""
        )

        results = await search_web(last_user_message)

        if results:
            context = "\n\n".join(
                [
                    f"عنوان: {item.get('title', '')}\n"
                    f"لینک: {item.get('url', '')}\n"
                    f"محتوا: {item.get('content', '')}"
                    for item in results
                ]
            )

            sources = [
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", "")
                }
                for item in results
                if item.get("url")
            ]

            messages.insert(
                0,
                {
                    "role": "system",
                    "content": (
                        "تو دستیار AURA هستی. "
                        "با استفاده از منابع زیر پاسخ دقیق بده. "
                        "اگر اطلاعات کافی نیست، صادقانه بگو. "
                        "منابع را جعل نکن.\n\n"
                        + context
                    )
                }
            )

    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.7
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                api_url,
                json=body,
                headers={
                    "Authorization": f"Bearer {api_key}"
                }
            )

        response.raise_for_status()

        data = response.json()

        reply = data["choices"][0]["message"]["content"]

        if sources:
            reply += "\n\n### منابع:\n"

            for source in sources:
                reply += (
                    f"- [{source['title']}]"
                    f"({source['url']})\n"
                )

        return {"reply": reply}

    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"خطای سرویس هوش مصنوعی: "
                f"{exc.response.status_code}"
            )
        )

    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        raise HTTPException(
            status_code=502,
            detail="ارتباط با سرویس هوش مصنوعی برقرار نشد."
  )
