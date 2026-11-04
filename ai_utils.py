"""File text extraction and AI helpers (chat, summary, quiz)."""

import io
import json
import os

import streamlit as st

MAX_DOC_CHARS = 16000   # how much of a document is sent to the AI (Groq free tier has small limits)


class AIError(Exception):
    """Raised with a user-friendly message when the AI call fails."""


# ---------------------------------------------------------------- extraction

def extract_text(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    data = uploaded_file.getvalue()

    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)

    if name.endswith(".docx"):
        from docx import Document

        doc = Document(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(parts)

    if name.endswith(".pptx"):
        from pptx import Presentation

        prs = Presentation(io.BytesIO(data))
        parts = []
        for number, slide in enumerate(prs.slides, start=1):
            parts.append(f"[Slide {number}]")
            for shape in slide.shapes:
                if shape.has_text_frame:
                    parts.append(shape.text_frame.text)
        return "\n".join(parts)

    return data.decode("utf-8", errors="ignore")


# ------------------------------------------------------------------- client

def _secret(name):
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    return value or os.getenv(name)


def ai_available() -> bool:
    return bool(_secret("GROQ_API_KEY"))


PREFERRED_MODELS = ["llama-3.3-70b-versatile", "openai/gpt-oss-20b", "llama-3.1-8b-instant"]
_SKIP_WORDS = ("whisper", "guard", "tts", "orpheus", "embed", "compound", "safeguard")
_WORKING_MODEL = None  # remembered after the first successful call


def _live_models(client) -> list:
    """Ask Groq which models exist right now (models change often)."""
    try:
        ids = [m.id for m in client.models.list().data]
    except Exception:
        return []
    ids = [i for i in ids if not any(w in i.lower() for w in _SKIP_WORDS)]
    order = ("llama-3.3-70b", "gpt-oss-120b", "gpt-oss-20b", "llama-3.1-8b", "qwen", "llama")

    def rank(model_id):
        low = model_id.lower()
        for position, word in enumerate(order):
            if word in low:
                return position
        return 99

    return sorted(ids, key=rank)


def ask_ai(system: str, messages: list, max_tokens: int = 1500) -> str:
    global _WORKING_MODEL

    key = _secret("GROQ_API_KEY")
    if not key:
        raise AIError("AI key is not set. Add GROQ_API_KEY in the app secrets.")

    import groq

    client = groq.Groq(api_key=key)
    full_messages = [{"role": "system", "content": system}] + messages
    tried, errors = [], []

    def run(models):
        global _WORKING_MODEL
        for model in models:
            if not model or model in tried:
                continue
            tried.append(model)
            try:
                response = client.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=full_messages,
                )
                _WORKING_MODEL = model
                return (response.choices[0].message.content or "").strip()
            except groq.AuthenticationError:
                raise AIError("The API key is invalid. Create a new key and update GROQ_API_KEY.")
            except groq.RateLimitError:
                raise AIError("Too many requests right now. Please wait a minute and try again.")
            except groq.APIConnectionError as error:
                raise AIError(
                    "Cannot connect to Groq (check internet / VPN / firewall). "
                    f"Details: {error}"
                )
            except groq.APIStatusError as error:
                errors.append(f"{model}: {error}")
                continue
            except groq.APIError as error:
                raise AIError(f"AI service error: {error}")
        return None

    first = [_WORKING_MODEL, _secret("GROQ_MODEL")] + PREFERRED_MODELS
    result = run(first)
    if result is None:
        result = run(_live_models(client)[:6])
    if result is None:
        detail = errors[0] if errors else "no model available"
        raise AIError(f"AI service error: {detail}")
    return result


# ---------------------------------------------------------------- features

def chat_reply(history: list, document_text: str | None) -> str:
    """history = [{'role': 'user'|'assistant', 'content': str}, ...]"""
    system = (
        "You are Study Buddy, a friendly tutor for university students. "
        "Explain in simple English with small daily-life examples. "
        "Keep answers clear and well organised."
    )
    if document_text:
        system += (
            "\n\nThe student uploaded the study material below. Base your answers on it. "
            "If the answer is not in the material, say so first, then help from general knowledge.\n\n"
            "=== STUDY MATERIAL ===\n" + document_text[:MAX_DOC_CHARS]
        )
    return ask_ai(system, history[-12:], max_tokens=1200)


SUMMARY_MODES = {
    "Short summary": "Write a short summary (about 150-200 words) in simple English.",
    "Key points and definitions": (
        "List the key points as bullet points, then a 'Key terms' section "
        "with one-line definitions."
    ),
    "Likely exam questions": (
        "Write 8 likely exam questions (mix of short and long answer) "
        "and give a model answer of 2-4 lines for each."
    ),
}


def summarize(document_text: str, mode: str) -> str:
    system = (
        "You are a study assistant. Use only the material provided. "
        "Use simple English and markdown formatting."
    )
    prompt = (
        f"{SUMMARY_MODES[mode]}\n\n=== STUDY MATERIAL ===\n{document_text[:MAX_DOC_CHARS]}"
    )
    return ask_ai(system, [{"role": "user", "content": prompt}], max_tokens=1800)


def generate_quiz(document_text: str, count: int, difficulty: str) -> list:
    system = (
        "You create multiple-choice exam questions from study material. "
        "Reply with JSON only: no explanation, no markdown fences."
    )
    prompt = (
        f"Create {count} {difficulty.lower()} multiple-choice questions from the material.\n"
        "Return a JSON array. Each item must be exactly:\n"
        '{"question": "...", "options": ["A text", "B text", "C text", "D text"], '
        '"answer_index": 0, "explanation": "one or two lines"}\n'
        "Rules: exactly 4 options, answer_index is 0-3, only one correct option, "
        "questions must come from the material.\n\n"
        f"=== STUDY MATERIAL ===\n{document_text[:MAX_DOC_CHARS]}"
    )
    raw = ask_ai(system, [{"role": "user", "content": prompt}], max_tokens=4000)

    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1:
        raise AIError("Could not read the quiz from the AI. Please try again.")
    try:
        items = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        raise AIError("Could not read the quiz from the AI. Please try again.")

    questions = []
    for item in items:
        try:
            options = [str(o) for o in item["options"]]
            answer = int(item["answer_index"])
            if len(options) == 4 and 0 <= answer < 4:
                questions.append(
                    {
                        "question": str(item["question"]),
                        "options": options,
                        "answer_index": answer,
                        "explanation": str(item.get("explanation", "")),
                    }
                )
        except (KeyError, TypeError, ValueError):
            continue

    if not questions:
        raise AIError("The AI returned no usable questions. Please try again.")
    return questions