from __future__ import annotations

import re
from typing import Any

_TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9_]{2,}")
_SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")
_STOP_WORDS = {
    "about", "after", "again", "also", "among", "an", "and", "are", "as", "at",
    "because", "before", "being", "between", "by", "can", "could", "do", "does",
    "each", "for", "from", "have", "in", "into", "is", "it", "must", "of", "on",
    "only", "or", "other", "over", "same", "should", "some", "such", "than",
    "that", "the", "their", "them", "then", "there", "these", "they", "this",
    "those", "through", "to", "under", "up", "very", "via", "what", "when",
    "where", "which", "while", "with", "within", "without", "would", "your",
}


def _normalise_token(token: str) -> str:
    """Apply a deliberately small plural normalisation for common English nouns."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith(("ches", "shes", "xes", "zes")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def _tokens(value: str) -> set[str]:
    return {
        _normalise_token(token.casefold())
        for token in _TOKEN_PATTERN.findall(value)
        if token.casefold() not in _STOP_WORDS
    }


def _sentences(value: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_PATTERN.split(value.strip()) if part.strip()]


def _record_text(dataset_type: str, payload: dict[str, Any]) -> tuple[str, str]:
    if dataset_type == "instruction":
        return payload.get("instruction", ""), payload.get("output", "")
    if dataset_type == "question_answer":
        return payload.get("question", ""), payload.get("answer", "")
    messages = payload.get("messages", [])
    prompt = " ".join(
        message.get("content", "")
        for message in messages
        if message.get("role") == "user"
    )
    answer = " ".join(
        message.get("content", "")
        for message in messages
        if message.get("role") == "assistant"
    )
    return prompt, answer


class DatasetQualityService:
    """Provide explainable heuristic checks; never auto-approve a dataset record."""

    @staticmethod
    def assess(
        dataset_type: str,
        payload: dict[str, Any],
        provenance: list[dict[str, Any]],
    ) -> dict[str, Any]:
        prompt, answer = _record_text(dataset_type, payload)
        prompt_tokens = _tokens(prompt)
        answer_tokens = _tokens(answer)
        sentences = _sentences(answer)
        flags: list[dict[str, Any]] = []

        if not prompt_tokens or not answer_tokens:
            flags.append({
                "code": "missing_content",
                "severity": "high",
                "message": "The instruction/question or answer has too little text to assess.",
            })
        elif not prompt_tokens.intersection(answer_tokens):
            flags.append({
                "code": "low_prompt_alignment",
                "severity": "high",
                "message": "The answer shares no key terms with the instruction or question.",
            })

        if len(answer.split()) < 4:
            flags.append({
                "code": "very_short_answer",
                "severity": "medium",
                "message": "The answer is very short; check that it is complete.",
            })
        if len(answer.split()) > 180:
            flags.append({
                "code": "long_answer",
                "severity": "medium",
                "message": "The answer is unusually long; check for unrelated detail.",
            })

        knowledge_items = [
            item for item in provenance
            if isinstance(item, dict) and isinstance(item.get("content"), str)
        ]
        if not knowledge_items:
            flags.append({
                "code": "missing_provenance",
                "severity": "high",
                "message": "No supporting knowledge content is available for quality review.",
            })
        else:
            combined_source_tokens: set[str] = set()
            relevant_items: list[set[str]] = []
            off_topic_items = []
            for item in knowledge_items:
                source_tokens = _tokens(item["content"])
                combined_source_tokens.update(source_tokens)
                if len(prompt_tokens.intersection(source_tokens)) >= 2:
                    relevant_items.append(source_tokens)
                else:
                    off_topic_items.append(item)

            if answer_tokens and not answer_tokens.intersection(combined_source_tokens):
                flags.append({
                    "code": "weak_source_overlap",
                    "severity": "medium",
                    "message": (
                        "The answer has little exact-word overlap with its supporting "
                        "knowledge. Check paraphrases and factual support manually."
                    ),
                })
            if len(knowledge_items) > 1 and off_topic_items:
                flags.append({
                    "code": "possibly_mixed_topics",
                    "severity": "high",
                    "message": (
                        f"{len(off_topic_items)} of {len(knowledge_items)} linked knowledge "
                        "items share fewer than two key terms with the instruction or "
                        "question. Check whether the record combines unrelated facts."
                    ),
                })

            flagged_sentences: list[str] = []
            if relevant_items:
                for sentence in sentences:
                    sentence_tokens = _tokens(sentence)
                    if not any(
                        len(sentence_tokens.intersection(source_tokens)) >= 2
                        for source_tokens in relevant_items
                    ):
                        flagged_sentences.append(sentence)
            elif sentences:
                flagged_sentences = sentences

            if flagged_sentences:
                flags.append({
                    "code": "off_topic_answer_sentence",
                    "severity": "high",
                    "message": (
                        f"{len(flagged_sentences)} answer sentence(s) do not appear "
                        "to be supported by knowledge relevant to the question."
                    ),
                    "sentences": flagged_sentences,
                })

        deductions = sum(
            30 if flag["severity"] == "high" else 15
            for flag in flags
        )
        score = max(0, 100 - deductions)
        return {
            "score": score,
            "label": (
                "Review carefully" if any(flag["severity"] == "high" for flag in flags)
                else "Looks consistent" if not flags
                else "Check warnings"
            ),
            "flags": flags,
            "method": "heuristic",
            "disclaimer": (
                "Heuristic screening only. Sentence and word overlap cannot prove "
                "semantic relevance or factual correctness. Review the answer and "
                "source evidence yourself."
            ),
        }
