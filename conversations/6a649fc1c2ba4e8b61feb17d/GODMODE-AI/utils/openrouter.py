"""
Project GODMODE — OpenRouter API Client
Enhanced with fallback chains, retry logic, streaming support, and token tracking.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Tuple

import requests

from utils.config import (
    OPENROUTER_API_KEY,
    MODELS,
    FALLBACK_CHAINS,
    get_system_prompt,
    is_image_model,
    IMAGE_MODEL_IDS,
    get_model_label,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
IMAGE_URL = "https://openrouter.ai/api/v1/images/generations"
MODELS_URL = "https://openrouter.ai/api/v1/models"

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://godmode-ai.vercel.app",
    "X-Title": "Project GODMODE",
}

MAX_RETRIES = 2
RETRY_DELAY = 1.5  # seconds
REQUEST_TIMEOUT = 55  # just under Vercel's 60s limit


# ──────────────────────────── TEXT GENERATION ────────────────────────────

def send_message(
    model: str,
    messages: List[Dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    stream: bool = False,
) -> Tuple[str, Optional[Dict]]:
    """
    Send a chat completion request to OpenRouter.
    Returns (response_text, usage_metadata).
    Automatically falls back to alternative models on failure.
    """
    if is_image_model(model):
        user_msgs = [m for m in messages if m.get("role") == "user"]
        if user_msgs:
            prompt = user_msgs[-1].get("content", "")
            url, meta = generate_image(model, prompt)
            return url, meta
        return "Error: No prompt for image generation.", None

    system_prompt = get_system_prompt(model)
    full_messages = [{"role": "system", "content": system_prompt}] + messages

    # Build fallback chain
    chain = [model] + FALLBACK_CHAINS.get(model, [MODELS["f1"], MODELS["f2"]])
    # Deduplicate while preserving order
    seen = set()
    chain = [m for m in chain if not (m in seen or seen.add(m))]

    last_error = ""
    for attempt, current_model in enumerate(chain):
        for retry in range(MAX_RETRIES + 1):
            try:
                payload = {
                    "model": current_model,
                    "messages": full_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "top_p": 0.95,
                    "frequency_penalty": 0.2,
                    "presence_penalty": 0.2,
                    "stream": stream,
                }

                response = requests.post(
                    BASE_URL, headers=HEADERS, json=payload, timeout=REQUEST_TIMEOUT
                )

                # Rate limited — wait and retry
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", RETRY_DELAY))
                    logger.warning(f"Rate limited on {current_model}, retrying in {retry_after}s")
                    if retry < MAX_RETRIES:
                        time.sleep(min(retry_after, 10))
                        continue
                    last_error = "Rate limited"
                    break

                response.raise_for_status()
                data = response.json()

                if "choices" in data and len(data["choices"]) > 0:
                    text = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {})
                    usage["model_used"] = current_model
                    if current_model != model:
                        usage["fallback_from"] = model
                        logger.info(f"Fell back from {model} to {current_model}")
                    return text, usage

                last_error = f"Empty response from {current_model}"
                break

            except requests.exceptions.Timeout:
                logger.warning(f"Timeout on {current_model} (retry {retry})")
                last_error = "timeout"
                if retry < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                    continue
                break

            except requests.exceptions.RequestException as e:
                err_msg = str(e)
                if hasattr(e, "response") and e.response is not None:
                    try:
                        err_data = e.response.json()
                        err_msg = err_data.get("error", {}).get("message", err_msg)
                    except Exception:
                        err_msg = f"{e.response.status_code}: {e.response.text[:200]}"

                logger.error(f"Error on {current_model}: {err_msg}")
                last_error = err_msg
                if retry < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                    continue
                break

        if attempt < len(chain) - 1:
            logger.info(f"Trying fallback model: {chain[attempt + 1]}")

    return f"⚠️ All models failed. Last error: {last_error}", None


# ──────────────────────────── STREAMING ────────────────────────────

def stream_message(
    model: str,
    messages: List[Dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
):
    """
    Generator that yields text chunks for real-time streaming.
    Falls back to non-streaming on error.
    """
    system_prompt = get_system_prompt(model)
    full_messages = [{"role": "system", "content": system_prompt}] + messages

    payload = {
        "model": model,
        "messages": full_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": 0.95,
        "stream": True,
    }

    try:
        response = requests.post(
            BASE_URL, headers=HEADERS, json=payload, timeout=REQUEST_TIMEOUT, stream=True
        )
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        import json
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except Exception:
                        continue
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        # Fall back to non-streaming
        text, _ = send_message(model, messages, temperature, max_tokens, stream=False)
        yield text


# ──────────────────────────── IMAGE GENERATION ────────────────────────────

def generate_image(model: str, prompt: str) -> Tuple[str, Optional[Dict]]:
    """
    Generate an image via OpenRouter.
    Returns (image_url_or_message, metadata).
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
    }

    try:
        response = requests.post(IMAGE_URL, headers=HEADERS, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        if "data" in data and len(data["data"]) > 0:
            image_url = data["data"][0].get("url")
            if image_url:
                meta = {"model_used": model, "type": "image", "prompt": prompt}
                return image_url, meta
            return "Error: No image URL in response.", None

        if "error" in data:
            return f"❌ {data['error'].get('message', 'Unknown error')}", None

        return "Error: Unexpected image response format.", None

    except requests.exceptions.Timeout:
        return "⚠️ Image generation timed out. Try a faster model (FLUX Schnell).", None
    except requests.exceptions.RequestException as e:
        err_msg = str(e)
        if hasattr(e, "response") and e.response is not None:
            try:
                err_data = e.response.json()
                err_msg = err_data.get("error", {}).get("message", err_msg)
            except Exception:
                err_msg = f"{e.response.status_code}"
        logger.error(f"Image generation error: {err_msg}")
        return f"❌ Image error: {err_msg}", None


# ──────────────────────────── MODEL LISTING ────────────────────────────

def list_available_models() -> List[str]:
    """Fetch all available model IDs from OpenRouter."""
    try:
        response = requests.get(MODELS_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        return [m["id"] for m in data.get("data", [])]
    except Exception as e:
        logger.error(f"Error fetching model list: {e}")
        return []


def get_model_info(model: str) -> Optional[Dict]:
    """Fetch details for a specific model from OpenRouter."""
    try:
        response = requests.get(f"{MODELS_URL}/{model}", headers=HEADERS, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None
