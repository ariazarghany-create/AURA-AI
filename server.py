import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aura")

app = FastAPI(title="AURA AI API", version="0.3.0")

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
        logger.error("TAVILY: API key is missing")
        raise HTTPException(
            status_code=503,
            detail="کلید جست‌وجوی Tavily تنظیم نشده است."
        )

    logger.info("TAVILY: Search request started")

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

        logger.info(
            "TAVILY: HTTP status %s",
            response.status_code
        )

        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])

        logger.info(
            "TAVILY: Results received: %s",
            len(results)
        )

        return results

    except httpx.HTTPStatusError as exc:
        logger.error(
            "TAVILY: HTTP error %s",
            exc.response.status_code
        )
        raise HTTPException(
            status_code=502,
            detail="سرویس جست‌وجوی اینترنتی خطا داد."
        )

    except (httpx.HTTPError, ValueError):
        logger.exception("TAVILY: Connection or response error")
        raise HTTPException(
            status_code=502,
            detail="ارتباط با سرویس جست‌وجوی اینترنتی برقرار نشد."
        )


@app.post("/api/chat")
async def chat(payload: ChatRequest):
    logger.info(
        "CHAT: Request received. web_search=%s",
        payload.web_search
    )

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

        query = last_user_message.strip()

        if query.startswith("جستجو:"):
            query = query[len("جستجو:"):].strip()

        if not query:
            raise HTTPException(
                status_code=400,
                detail="عبارت جست‌وجو خالی است."
            )

        results = await search_web(query)

        if not results:
            logger.warning("TAVILY: No search results found")
            raise HTTPException(
                status_code=502,
                detail="جست‌وجو انجام شد، اما نتیجه‌ای پیدا نشد."
            )

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
                    "کاربر درخواست جست‌وجوی اینترنتی داده است. "
                    "از اطلاعات و منابع زیر برای پاسخ استفاده کن. "
                    "اطلاعات قدیمی را به‌عنوان خبر جدید معرفی نکن. "
                    "اگر منابع کافی نیستند، صادقانه بگو. "
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

        logger.info("CHAT: Response generated successfully")
        return {"reply": reply}

    except httpx.HTTPStatusError as exc:
        logger.error(
            "AI: HTTP error %s",
            exc.response.status_code
        )
        raise HTTPException(
            status_code=502,
            detail=(
                f"خطای سرویس هوش مصنوعی: "
                f"{exc.response.status_code}"
            )
        )

    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        logger.exception("AI: Request or response error")
        raise HTTPException(
            status_code=502,
            detail="ارتباط با سرویس هوش مصنوعی برقرار نشد."
    )
