from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
import requests
import os
import json
import uuid
from pathlib import Path

_env = Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODEL = "z-ai/glm4.7"  # or "meta-llama/llama-3.2-3b-instruct"

app = FastAPI()

@app.post("/v1/messages")
async def messages(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    max_tokens = body.get("max_tokens", 4096)

    oai_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            text = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
        else:
            text = content
        oai_messages.append({"role": role, "content": text})

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": MODEL,
            "messages": oai_messages,
            "max_tokens": max_tokens
        },
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    return JSONResponse({
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": content}],
        "model": MODEL,
        "stop_reason": "end_turn",
        "usage": data.get("usage", {})
    })

@app.get("/v1/models")
async def list_models():
    return JSONResponse({"data": [{"id": MODEL}]})

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=4000)