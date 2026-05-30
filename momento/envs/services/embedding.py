from __future__ import annotations

from sentence_transformers import SentenceTransformer

_MODEL_NAME = "microsoft/harrier-oss-v1-0.6b"

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(_MODEL_NAME, model_kwargs={"dtype": "auto"})
    return _model


def embed_text(text: str, instruction: str | None = None) -> list[float]:
    kwargs: dict = {}
    if instruction:
        kwargs["prompt"] = instruction
    return _get_model().encode(text, **kwargs).tolist()


def embed_texts(texts: list[str], instruction: str | None = None) -> list[list[float]]:
    kwargs: dict = {"batch_size": 32}
    if instruction:
        kwargs["prompt"] = instruction
    return _get_model().encode(texts, **kwargs).tolist()


def build_session_text(summary: str, extracted_facts: dict) -> str:
    parts = [summary]
    for key, val in extracted_facts.items():
        if val:
            parts.append(f"{key}: {val}")
    return "\n".join(parts)


def to_pg_vector(embedding: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"
