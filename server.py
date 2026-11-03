import os
from typing import List, Literal
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="AURA AI API", version="0.1.0")
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

@app.get("/health")
async def health():
    return {"status": "ok", "service": "AURA AI"}

@app.post("/api/chat")
async def chat(payload: ChatRequest):
    api_key = os.getenv("AI_API_KEY")
    api_url = os.getenv("AI_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("AI_MODEL", "gpt-4o-mini")
    if not api_key:
        raise HTTPException(status_code=503, detail="کلید API روی سرور تنظیم نشده است.")
    body = {"model": model, "messages": [m.model_dump() for m in payload.messages], "temperature": 0.7}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(api_url, json=body, headers={"Authorization": f"Bearer {api_key}"})
        response.raise_for_status()
        data = response.json()
        reply = data["choices"][0]["message"]["content"]
        return {"reply": reply}
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"خطای سرویس هوش مصنوعی: {exc.response.status_code}")
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        raise HTTPException(status_code=502, detail="ارتباط با سرویس هوش مصنوعی برقرار نشد.")
