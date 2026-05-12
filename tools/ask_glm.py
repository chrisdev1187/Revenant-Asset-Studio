"""
GLM chat via NVIDIA NIM — token-saving companion to Claude Code.

Usage:
    python tools/ask_glm.py              # interactive REPL
    python tools/ask_glm.py "question"  # one-shot

Reads NVIDIA_API_KEY from .env in the project root.
Model can be changed via GLM_MODEL env var or by editing MODEL below.

Available GLM models on NVIDIA NIM:
    z-ai/glm4.7   ← default
    z-ai/glm5
    z-ai/glm-5.1
"""

import os
import sys
from pathlib import Path

# ── Load .env ──────────────────────────────────────────────────────────────────
_env = Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get("NVIDIA_API_KEY", "")
MODEL   = os.environ.get("GLM_MODEL", "z-ai/glm-5.1")

if not API_KEY:
    print("[ERR] NVIDIA_API_KEY not found in .env")
    sys.exit(1)

from openai import OpenAI

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=API_KEY,
)


def ask(messages: list[dict]) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=2048,
        temperature=0.7,
    )
    return resp.choices[0].message.content


def repl():
    global MODEL
    print(f"GLM chat  [{MODEL}]  —  /clear  /exit  /model <id>")
    print("-" * 60)
    history: list[dict] = []

    while True:
        try:
            user_in = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            break

        if not user_in:
            continue
        if user_in.lower() in ("/exit", "/quit", "exit", "quit"):
            break
        if user_in.lower() == "/clear":
            history.clear()
            print("[history cleared]")
            continue
        if user_in.lower().startswith("/model "):
            MODEL = user_in[7:].strip()
            print(f"[model → {MODEL}]")
            continue

        history.append({"role": "user", "content": user_in})
        try:
            reply = ask(history)
        except Exception as exc:
            print(f"[ERR] {exc}")
            history.pop()
            continue
        history.append({"role": "assistant", "content": reply})
        print(f"\nGLM: {reply}\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # One-shot mode
        question = " ".join(sys.argv[1:])
        print(ask([{"role": "user", "content": question}]))
    else:
        repl()
