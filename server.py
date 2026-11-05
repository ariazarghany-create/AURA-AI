import os
import re
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

app = FastAPI(title="AURA AI API", version="0.4.0")
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


def should_search_web(text: str) -> bool:
    """تشخیص تقریبی پیام‌هایی که به اطلاعات روز یا اینترنت نیاز دارند."""
    text = text.strip().lower()

    if text.startswith(("جستجو:", "جستجو：", "search:")):
        return True

    keywords = [
        "آخرین", "جدیدترین", "امروز", "اکنون", "همین الان",
        "امسال", "دیروز", "فردا", "اخبار", "خبر", "قیمت",
        "نرخ", "ارز", "دلار", "یورو", "طلا", "آب و هوا",
        "هواشناسی", "وضعیت فعلی", "اطلاعات به‌روز",
        "اطلاعات بروز", "آپدیت", "به‌روزرسانی",
        "نتایج جدید", "چه خبر", "کی منتشر", "زمان انتشار",
        "latest", "current", "today", "now", "recent",
        "news", "price", "weather", "exchange rate",
        "stock price", "updates", "this week", "this month",
    ]
    return any(keyword in text for keyword in keywords)


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
                    "include_answer": False,
                },
            )
        logger.info("TAVILY: HTTP status %s", response.status_code)
        response.raise_for_status()
        results = response.json().get("results", [])
        logger.info("TAVILY: Results received: %s", len(results))
        return results

    except httpx.HTTPStatusError as exc:
        logger.error("TAVILY: HTTP error %s", exc.response.status_code)
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
    last_user_message = next(
        (m.content for m in reversed(payload.messages) if m.role == "user"),
        "",
    )
    web_search = payload.web_search or should_search_web(last_user_message)
    logger.info("CHAT: Request received. web_search=%s", web_search)

    api_key = os.getenv("AI_API_KEY")
    api_url = os.getenv(
        "AI_API_URL",
        "https://api.openai.com/v1/chat/completions",
    )
    model = os.getenv("AI_MODEL", "gpt-4o-mini")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="کلید هوش مصنوعی روی سرور تنظیم نشده است."
        )

    messages = [m.model_dump() for m in payload.messages]
    current_time = datetime.now(
        ZoneInfo("Asia/Tehran")
    ).strftime("%Y-%m-%d %H:%M")

    system_content = (
        f"تاریخ و زمان فعلی: {current_time}. "
        "منطقه زمانی: تهران، ایران. "
        "این تاریخ مرجع زمان فعلی است. "
        "تو دستیار هوشمند AURA هستی. "
        "پاسخ‌ها را دقیق، روشن و به زبان کاربر ارائه کن. "
        "اطلاعات نامطمئن را به‌عنوان واقعیت قطعی بیان نکن."
    )
    sources = []

    if web_search:
        query = re.sub(
            r"^(جستجو|search)\s*[:：]\s*",
            "",
            last_user_message.strip(),
            flags=re.IGNORECASE,
        )
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
            f"عنوان: {item.get('title', '')}\n"
            f"لینک: {item.get('url', '')}\n"
            f"محتوا: {item.get('content', '')}"
            for item in results
        )
        sources = [
            {"title": item.get("title", ""), "url": item.get("url", "")}
            for item in results if item.get("url")
        ]
        system_content += (
            "\nکاربر درباره موضوعی نیازمند اطلاعات به‌روز پرسیده است. "
            "از نتایج جست‌وجوی زیر برای پاسخ استفاده کن. "
            "اطلاعات قدیمی را به‌عنوان خبر جدید معرفی نکن. "
            "اگر منابع کافی نیستند، صادقانه اعلام کن. "
            "اطلاعات یا منبعی را جعل نکن.\n\n"
            "نتایج جست‌وجوی اینترنتی:\n" + context
        )

    messages.insert(0, {"role": "system", "content": system_content})
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                api_url,
                json=body,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        response.raise_for_status()
        data = response.json()
        reply = data["choices"][0]["message"]["content"]

        if not isinstance(reply, str):
            raise ValueError("AI response content is not text")

        if sources:
            reply += "\n\n### منابع:\n"
            for source in sources:
                title = source["title"] or source["url"]
                reply += f"- [{title}]({source['url']})\n"

        logger.info("CHAT: Response generated successfully")
        return {"reply": reply}

    except httpx.HTTPStatusError as exc:
        logger.error("AI: HTTP error %s", exc.response.status_code)
        raise HTTPException(
            status_code=502,
            detail=f"خطای سرویس هوش مصنوعی: {exc.response.status_code}",
        )
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        logger.exception("AI: Request or response error")
        raise HTTPException(
            status_code=502,
            detail="ارتباط با سرویس هوش مصنوعی برقرار نشد."
)
