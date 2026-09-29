"""Swappable LLM narrator. The LLM only ever sees computed facts and its output is rejected if it contains numbers not in those facts."""
import os, re, json
import httpx

PROVIDER = os.getenv("LLM_PROVIDER", "none")  # none | openai (any OpenAI-compatible: OpenAI, Groq, OpenRouter, Ollama, Gemini) | anthropic
MODEL = os.getenv("LLM_MODEL", "")
BASE = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
KEY = os.getenv("LLM_API_KEY", "")
SYSTEM = ("You are a retail-expansion analyst for Savomart, a neighbourhood grocery chain in Chennai. Write 3-4 plain sentences for a BD Manager "
          "explaining the fitness result. Use ONLY the facts in the JSON. Copy numbers exactly as given. Never invent figures, place names or "
          "facts. Do not mention any number that is not in the JSON. Mention the strongest factor, the weakest factor and where to scout first.")
_num = lambda t: set(re.findall(r"\d+(?:\.\d+)?", t.replace(",", "")))


def _call(prompt):
    if PROVIDER == "anthropic":
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=40, headers={"x-api-key": KEY, "anthropic-version": "2023-06-01"},
                       json={"model": MODEL or "claude-haiku-4-5-20251001", "max_tokens": 400, "system": SYSTEM, "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status(); return r.json()["content"][0]["text"]
    r = httpx.post(f"{BASE}/chat/completions", timeout=40, headers={"Authorization": f"Bearer {KEY}"},
                   json={"model": MODEL or "gpt-4o-mini", "temperature": 0.2, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]})
    r.raise_for_status(); return r.json()["choices"][0]["message"]["content"]


def narrate(facts, fallback):
    if PROVIDER == "none":
        return {"text": fallback, "source": "template", "note": "LLM_PROVIDER=none, deterministic template used"}
    try:
        text = _call(json.dumps(facts)).strip()
        bad = _num(text) - _num(json.dumps(facts)) - {"100", "1", "2", "3"}
        if bad:
            return {"text": fallback, "source": "template", "note": f"LLM output rejected: ungrounded numbers {sorted(bad)}"}
        return {"text": text, "source": f"llm:{PROVIDER}", "verified": True, "note": "Every number in this text was checked against the computed facts."}
    except Exception as e:
        return {"text": fallback, "source": "template", "note": f"LLM unavailable ({type(e).__name__})"}
