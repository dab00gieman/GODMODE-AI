"""Summarizer Skill — extractive text summarization."""

import re
import logging
from collections import Counter

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "this", "that", "it", "he", "she", "they", "we", "you", "i",
    "be", "been", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "can", "shall",
    "not", "no", "if", "then", "so", "than", "too", "very", "just",
    "about", "above", "after", "again", "all", "also", "any", "each",
    "few", "more", "most", "other", "some", "such", "only", "own",
    "same", "up", "down", "out", "over", "under",
}


def run(text: str, max_sentences: int = 3) -> str:
    """Extractive summarization using word frequency scoring."""
    if not text or len(text) < 200:
        return text if text else "Error: No text provided."

    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    if len(sentences) <= max_sentences:
        return text.strip()

    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    word_freq = Counter(w for w in words if w not in STOP_WORDS)

    scored = []
    for i, sentence in enumerate(sentences):
        score = 0
        sentence_words = re.findall(r'\b[a-zA-Z]{3,}\b', sentence.lower())
        for word in sentence_words:
            if word in word_freq:
                score += word_freq[word]

        if len(sentence_words) > 0:
            score = score / len(sentence_words)
            if i < 3:
                score *= 1.2

        scored.append((i, sentence, score))

    top = sorted(scored, key=lambda x: x[2], reverse=True)[:max_sentences]
    top.sort(key=lambda x: x[0])

    summary = " ".join(s[1] for s in top)
    return f"Summary ({max_sentences} key points):\n\n{summary}"
