"""
Project GODMODE — Firebase Firestore Memory Management
Replaces the previous Redis-based system with Firebase Firestore.
Handles: sessions, user prefs, usage stats, rate limiting, learned skills, episodic memory, MEMORY.md.

Task 8: Episodic memory upgraded from keyword overlap to embedding-based semantic search.
Uses OpenRouter embeddings API to generate and store vectors alongside episodes.
At search time, embeds the query and ranks by cosine similarity.
"""

import json
import logging
import time
import math
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ──────────────────────────── FIREBASE INIT ────────────────────────────

_firestore_db = None

def _init_firebase():
    """Initialize Firebase Admin SDK and return Firestore client."""
    global _firestore_db
    if _firestore_db is not None:
        return _firestore_db

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        # Check if already initialized
        try:
            app = firebase_admin.get_app()
        except ValueError:
            # Build credentials from env vars
            project_id = os.getenv("FIREBASE_PROJECT_ID", "")
            client_email = os.getenv("FIREBASE_CLIENT_EMAIL", "")
            private_key = os.getenv("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n")

            if not project_id or not client_email or not private_key:
                logger.warning("Firebase credentials not fully configured — memory features will degrade gracefully")
                return None

            cred = credentials.Certificate({
                "type": "service_account",
                "project_id": project_id,
                "private_key": private_key,
                "client_email": client_email,
                "token_uri": "https://oauth2.googleapis.com/token",
            })
            firebase_admin.initialize_app(cred)

        _firestore_db = firestore.client()
        logger.info("Firebase Firestore connection established.")
        return _firestore_db

    except Exception as e:
        logger.error(f"Firebase initialization failed: {e}")
        return None


def get_db():
    """Get the Firestore client (or None if unavailable)."""
    return _init_firebase()


def get_redis_client():
    """Compatibility shim — returns Firestore client for modules that still call this."""
    return get_db()


# ──────────────────────────── CONSTANTS ────────────────────────────

SESSION_TTL_DAYS = 7
MAX_HISTORY_MESSAGES = 50

# Task 8: Embedding model for semantic search
EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDING_DIM = 1536  # dimension of text-embedding-3-small
EMBEDDING_URL = "https://openrouter.ai/api/v1/embeddings"


# ──────────────────────────── EMBEDDINGS (Task 8) ────────────────────────────

def _get_headers():
    """Get OpenRouter API headers for embedding calls."""
    from utils.config import OPENROUTER_API_KEY
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://godmode-ai.vercel.app",
        "X-Title": "Project GODMODE",
    }


def generate_embedding(text: str) -> List[float]:
    """
    Generate an embedding vector for the given text using OpenRouter.
    Falls back to None on failure — callers should handle gracefully.
    """
    if not text or len(text.strip()) < 3:
        return []

    try:
        import requests
        headers = _get_headers()
        payload = {
            "model": EMBEDDING_MODEL,
            "input": text[:8000],  # Cap at 8000 chars for the embedding
        }
        resp = requests.post(EMBEDDING_URL, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if "data" in data and len(data["data"]) > 0:
            return data["data"][0].get("embedding", [])
        return []
    except Exception as e:
        logger.warning(f"Embedding generation failed: {e}")
        return []


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


# ──────────────────────────── SESSION ────────────────────────────

def get_session(chat_id: int) -> List[Dict]:
    """Retrieve conversation history for a chat."""
    db = get_db()
    if not db:
        return []
    try:
        doc = db.collection("sessions").document(str(chat_id)).get()
        if doc.exists:
            data = doc.to_dict()
            messages = data.get("messages", [])
            # Trim to max history
            if len(messages) > MAX_HISTORY_MESSAGES:
                messages = messages[-MAX_HISTORY_MESSAGES:]
            return messages
        return []
    except Exception as e:
        logger.error(f"Error getting session {chat_id}: {e}")
        return []


def save_session(chat_id: int, messages: List[Dict]) -> bool:
    """Save conversation history for a chat."""
    db = get_db()
    if not db:
        return False
    try:
        # Trim to max history
        trimmed = messages[-MAX_HISTORY_MESSAGES:]
        db.collection("sessions").document(str(chat_id)).set({
            "messages": trimmed,
            "chat_id": chat_id,
            "updated_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(days=SESSION_TTL_DAYS),
        })
        return True
    except Exception as e:
        logger.error(f"Error saving session {chat_id}: {e}")
        return False


def clear_session(chat_id: int) -> bool:
    """Clear conversation history for a chat."""
    db = get_db()
    if not db:
        return False
    try:
        db.collection("sessions").document(str(chat_id)).delete()
        return True
    except Exception as e:
        logger.error(f"Error clearing session {chat_id}: {e}")
        return False


def get_session_info(chat_id: int) -> Dict:
    """Get session metadata."""
    db = get_db()
    if not db:
        return {"active": False, "message_count": 0, "expires_in": "N/A"}
    try:
        doc = db.collection("sessions").document(str(chat_id)).get()
        if doc.exists:
            data = doc.to_dict()
            msg_count = len(data.get("messages", []))
            expires = data.get("expires_at")
            if expires:
                now = datetime.utcnow()
                if hasattr(expires, 'tzinfo'):
                    from datetime import timezone
                    now = now.replace(tzinfo=timezone.utc)
                delta = expires - now
                expires_in = f"{delta.total_seconds() / 3600:.1f} hours"
            else:
                expires_in = "N/A"
            return {"active": msg_count > 0, "message_count": msg_count, "expires_in": expires_in}
        return {"active": False, "message_count": 0, "expires_in": "N/A"}
    except Exception as e:
        logger.error(f"Error getting session info {chat_id}: {e}")
        return {"active": False, "message_count": 0, "expires_in": "N/A"}


# ──────────────────────────── USER PREFERENCES ────────────────────────────

def get_prefs(chat_id: int) -> Dict:
    """Get user preferences."""
    db = get_db()
    if not db:
        return {}
    try:
        doc = db.collection("prefs").document(str(chat_id)).get()
        if doc.exists:
            return doc.to_dict()
        return {}
    except Exception as e:
        logger.error(f"Error getting prefs {chat_id}: {e}")
        return {}


def set_prefs(chat_id: int, **kwargs) -> bool:
    """Set user preferences."""
    db = get_db()
    if not db:
        return False
    try:
        doc_ref = db.collection("prefs").document(str(chat_id))
        doc = doc_ref.get()
        if doc.exists:
            doc_ref.update(kwargs)
        else:
            kwargs["chat_id"] = chat_id
            doc_ref.set(kwargs)
        return True
    except Exception as e:
        logger.error(f"Error setting prefs {chat_id}: {e}")
        return False


# ──────────────────────────── USAGE STATS ────────────────────────────

def record_usage(chat_id: int, model: str, tokens: int, msg_type: str = "text") -> bool:
    """Record usage for rate limiting and stats."""
    db = get_db()
    if not db:
        return False
    try:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        usage_id = f"{chat_id}_{today}"
        doc_ref = db.collection("usage").document(usage_id)

        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            doc_ref.update({
                "messages": data.get("messages", 0) + 1,
                "tokens": data.get("tokens", 0) + tokens,
                "images": data.get("images", 0) + (1 if msg_type == "image" else 0),
                "agent_turns": data.get("agent_turns", 0) + (1 if msg_type == "agent" else 0),
                "last_model": model,
                "last_used": datetime.utcnow(),
            })
        else:
            doc_ref.set({
                "chat_id": chat_id,
                "date": today,
                "messages": 1,
                "tokens": tokens,
                "images": 1 if msg_type == "image" else 0,
                "agent_turns": 1 if msg_type == "agent" else 0,
                "last_model": model,
                "last_used": datetime.utcnow(),
            })
        return True
    except Exception as e:
        logger.error(f"Error recording usage {chat_id}: {e}")
        return False


def get_user_stats(chat_id: int) -> Dict:
    """Get today's usage stats for a user."""
    db = get_db()
    if not db:
        return {"messages_today": 0, "tokens_today": 0, "images_today": 0}
    try:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        doc = db.collection("usage").document(f"{chat_id}_{today}").get()
        if doc.exists:
            data = doc.to_dict()
            return {
                "messages_today": data.get("messages", 0),
                "tokens_today": data.get("tokens", 0),
                "images_today": data.get("images", 0),
                "agent_turns": data.get("agent_turns", 0),
            }
        return {"messages_today": 0, "tokens_today": 0, "images_today": 0}
    except Exception as e:
        logger.error(f"Error getting user stats {chat_id}: {e}")
        return {"messages_today": 0, "tokens_today": 0, "images_today": 0}


def get_global_stats() -> Dict:
    """Get global usage stats for today."""
    db = get_db()
    if not db:
        return {"total_messages_today": 0, "total_tokens_today": 0}
    try:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        docs = db.collection("usage").stream()
        total_messages = 0
        total_tokens = 0
        for doc in docs:
            data = doc.to_dict()
            if data.get("date") == today:
                total_messages += data.get("messages", 0)
                total_tokens += data.get("tokens", 0)
        return {
            "total_messages_today": total_messages,
            "total_tokens_today": total_tokens,
        }
    except Exception as e:
        logger.error(f"Error getting global stats: {e}")
        return {"total_messages_today": 0, "total_tokens_today": 0}


# ──────────────────────────── RATE LIMITING ────────────────────────────

def check_rate_limit(chat_id: int, is_image: bool = False) -> Dict:
    """Check if user is within rate limits."""
    db = get_db()
    if not db:
        return {"allowed": True, "reset_in": 0}

    try:
        from utils.config import RATE_LIMIT
        today = datetime.utcnow().strftime("%Y-%m-%d")
        doc = db.collection("usage").document(f"{chat_id}_{today}").get()

        if not doc.exists:
            return {"allowed": True, "reset_in": 0}

        data = doc.to_dict()
        messages = data.get("messages", 0)
        images = data.get("images", 0)

        if is_image and images >= RATE_LIMIT.image_max:
            reset_in = 3600  # seconds until reset
            return {"allowed": False, "reset_in": reset_in}

        if messages >= RATE_LIMIT.max_messages:
            reset_in = 3600
            return {"allowed": False, "reset_in": reset_in}

        return {"allowed": True, "reset_in": 0}
    except Exception as e:
        logger.error(f"Error checking rate limit {chat_id}: {e}")
        return {"allowed": True, "reset_in": 0}


# ──────────────────────────── LEARNED SKILLS ────────────────────────────

def get_all_learned_skills() -> List[Dict]:
    """Retrieve all learned skills from Firestore."""
    db = get_db()
    if not db:
        return []
    try:
        docs = db.collection("learned_skills").stream()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        logger.error(f"Error getting learned skills: {e}")
        return []


def save_learned_skill(name: str, data: Dict) -> bool:
    """Save a learned skill to Firestore."""
    db = get_db()
    if not db:
        return False
    try:
        data["created_at"] = datetime.utcnow()
        db.collection("learned_skills").document(name).set(data)
        return True
    except Exception as e:
        logger.error(f"Error saving learned skill {name}: {e}")
        return False


def get_learned_skill(name: str) -> Optional[Dict]:
    """Get a specific learned skill."""
    db = get_db()
    if not db:
        return None
    try:
        doc = db.collection("learned_skills").document(name).get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        logger.error(f"Error getting learned skill {name}: {e}")
        return None


def delete_learned_skill_db(name: str) -> bool:
    """Delete a learned skill from Firestore."""
    db = get_db()
    if not db:
        return False
    try:
        db.collection("learned_skills").document(name).delete()
        return True
    except Exception as e:
        logger.error(f"Error deleting learned skill {name}: {e}")
        return False


# ──────────────────────────── EPISODIC MEMORY (Task 8 — semantic search) ────────────────────────────

def store_episodic(
    chat_id: int,
    query: str,
    summary: str,
    tools_used: List[str],
    topics: List[str] = None,
) -> bool:
    """
    Store an interaction in episodic memory.
    Task 8: Generates an embedding of query + summary for semantic search.
    Falls back to keyword-only storage if embedding generation fails.
    """
    db = get_db()
    if not db:
        return False
    try:
        # Task 8: Generate embedding for semantic search
        embedding_text = f"{query} {summary}"
        embedding = generate_embedding(embedding_text)

        doc_data = {
            "chat_id": chat_id,
            "query": query[:500],
            "summary": summary[:1000],
            "tools_used": tools_used,
            "topics": topics or [],
            "timestamp": datetime.utcnow(),
            "embedding": embedding,  # May be empty list if generation failed
        }

        db.collection("episodic").add(doc_data)
        logger.info(f"Episodic memory stored for chat {chat_id} (embedding: {len(embedding)} dims)")
        return True
    except Exception as e:
        logger.error(f"Failed to store episode: {e}")
        return False


def search_episodic(query: str, max_results: int = 3) -> List[Dict]:
    """
    Search episodic memory using semantic similarity (Task 8).

    If embeddings are available, generates an embedding for the query and
    ranks stored episodes by cosine similarity.
    Falls back to keyword overlap search if embeddings are unavailable.
    """
    db = get_db()
    if not db:
        return []
    try:
        # Get recent episodes
        docs = db.collection("episodic").order_by("timestamp", direction="DESCENDING").limit(50).stream()
        episodes = [doc.to_dict() for doc in docs]

        if not episodes:
            return []

        # Task 8: Try semantic search with embeddings first
        query_embedding = generate_embedding(query)

        if query_embedding:
            # Semantic search — rank by cosine similarity
            results = []
            for episode in episodes:
                ep_embedding = episode.get("embedding", [])

                if ep_embedding and len(ep_embedding) == len(query_embedding):
                    score = _cosine_similarity(query_embedding, ep_embedding)
                else:
                    # No embedding for this episode — fall back to keyword overlap
                    query_words = set(query.lower().split())
                    ep_text = (
                        episode.get("summary", "").lower()
                        + " " + episode.get("query", "").lower()
                    )
                    ep_words = set(ep_text.split())
                    overlap = len(query_words & ep_words)
                    score = overlap / max(len(query_words), 1) * 0.5  # Lower weight for keyword fallback

                if score > 0.01:  # Threshold to filter irrelevant results
                    ts = episode.get("timestamp")
                    ts_str = ts.strftime("%Y-%m-%d") if isinstance(ts, datetime) else "unknown"
                    results.append({
                        "summary": episode.get("summary", ""),
                        "query": episode.get("query", ""),
                        "timestamp": ts_str,
                        "score": round(score, 4),
                        "tools_used": episode.get("tools_used", []),
                    })

            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:max_results]

        # Fallback: keyword overlap search (original behavior)
        logger.info("Semantic search unavailable — falling back to keyword overlap")
        query_words = set(query.lower().split())

        results = []
        for episode in episodes:
            episode_text = (
                episode.get("summary", "").lower()
                + " " + episode.get("query", "").lower()
                + " " + " ".join(episode.get("topics", []))
            )
            episode_words = set(episode_text.split())
            overlap = len(query_words & episode_words)

            if overlap > 0:
                score = overlap / max(len(query_words), 1)
                ts = episode.get("timestamp")
                ts_str = ts.strftime("%Y-%m-%d") if isinstance(ts, datetime) else "unknown"
                results.append({
                    "summary": episode.get("summary", ""),
                    "query": episode.get("query", ""),
                    "timestamp": ts_str,
                    "score": score,
                    "tools_used": episode.get("tools_used", []),
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:max_results]
    except Exception as e:
        logger.warning(f"Episodic memory search failed: {e}")
        return []


# ──────────────────────────── MEMORY.md ────────────────────────────

def get_memory_md() -> str:
    """Read MEMORY.md from Firestore."""
    db = get_db()
    if not db:
        return ""
    try:
        doc = db.collection("memory").document("MEMORY.md").get()
        if doc.exists:
            content = doc.to_dict().get("content", "")
            return content
        return ""
    except Exception as e:
        logger.warning(f"Could not read MEMORY.md: {e}")
        return ""


def set_memory_md(content: str) -> bool:
    """Write MEMORY.md to Firestore."""
    db = get_db()
    if not db:
        return False
    try:
        db.collection("memory").document("MEMORY.md").set({
            "content": content,
            "updated_at": datetime.utcnow(),
        })
        return True
    except Exception as e:
        logger.error(f"Failed to update MEMORY.md: {e}")
        return False


def append_memory_md(content: str) -> bool:
    """Append to MEMORY.md in Firestore."""
    existing = get_memory_md()
    updated = existing + "\n\n" + content if existing else content
    return set_memory_md(updated)
