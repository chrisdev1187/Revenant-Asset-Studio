from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
import requests
import os
import json
import uuid
from pathlib import Path

# Load .env from parent folder
_env = Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

NVIDIA_KEY = os.environ.get("NVIDIA_API_KEY", "")
GLM_MODEL = "z-ai/glm4.7"   # confirmed working from your models list

if not NVIDIA_KEY:
    print("[proxy] ERROR: NVIDIA_API_KEY not found in .env")
    exit(1)

app = FastAPI()

@app.post("/v1/messages")
async def messages(request: Request):
    body = await request.json()
    print(f"[proxy] Received: {json.dumps(body, indent=2)[:200]}")

    # Convert Anthropic messages to OpenAI format
    oai_messages = []
    for msg in body.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            text = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
        else:
            text = content
        oai_messages.append({"role": role, "content": text})

    # Prepare payload for NVIDIA
    payload = {
        "model": GLM_MODEL,
        "messages": oai_messages,
        "max_tokens": body.get("max_tokens", 4096),
        "stream": False
    }

    try:
        print(f"[proxy] Calling NVIDIA with model {GLM_MODEL}...")
        resp = requests.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {NVIDIA_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )
        resp.raise_for_status()
        nv_data = resp.json()
        print(f"[proxy] NVIDIA responded")

        # Convert back to Anthropic format
        content = nv_data["choices"][0]["message"]["content"]
        anthropic_response = {
            "id": f"msg_{uuid.uuid4().hex[:24]}",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": content}],
            "model": GLM_MODEL,
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": nv_data.get("usage", {}).get("prompt_tokens", 0),
                "output_tokens": nv_data.get("usage", {}).get("completion_tokens", 0)
            }
        }
        return JSONResponse(anthropic_response)

    except Exception as e:
        print(f"[proxy] Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/v1/models")
async def list_models():
    return JSONResponse({
        "data": [
            {"id": GLM_MODEL, "object": "model", "created": 0, "owned_by": "nvidia"}
        ]
    })

@app.api_route("/{path:path}", methods=["GET","POST","PUT","DELETE","OPTIONS"])
async def catch_all(path: str):
    print(f"[proxy] Unhandled path: /{path}")
    return JSONResponse({"error": "not implemented"}, status_code=404)

if __name__ == "__main__":
    print(f"[proxy] Starting on port 4000 with model {GLM_MODEL}")
    uvicorn.run(app, host="127.0.0.1", port=4000, log_level="info")