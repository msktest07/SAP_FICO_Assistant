from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.parse
import urllib.request
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from tempfile import gettempdir
from typing import Tuple

from flask import Flask, jsonify, request, send_from_directory, abort


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"


def resolve_database_path() -> Path:
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return Path(gettempdir()) / "sap_fico.db"
    return ROOT / "sap_fico.db"


DATABASE = resolve_database_path()

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")

MAX_BODY_BYTES = 32_000


KNOWLEDGE = []
try:
    # import knowledge from the top-level app.py if present to keep a single source of truth
    from app import KNOWLEDGE as _K

    KNOWLEDGE = _K
except Exception:
    KNOWLEDGE = []


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect()) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                topic TEXT NOT NULL,
                module TEXT NOT NULL,
                product TEXT NOT NULL,
                release_name TEXT NOT NULL,
                country TEXT NOT NULL,
                confidence INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                rating TEXT NOT NULL CHECK (rating IN ('helpful', 'not_helpful')),
                comment TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(conversation_id),
                FOREIGN KEY(conversation_id) REFERENCES conversations(id)
            );
            """
        )


initialize_database()


def normalize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9./-]+", value.lower())


def summarize_web_text(text: str, max_chars: int = 360) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        return cleaned
    fragments = re.split(r"(?<=[.!?])\s+", cleaned)
    summary = ""
    for fragment in fragments:
        candidate = f"{summary} {fragment}".strip()
        if len(candidate) <= max_chars:
            summary = candidate
        else:
            break
    if not summary:
        summary = cleaned[: max_chars - 3].rstrip() + "..."
    if summary and summary[-1] not in ".!?":
        summary += "."
    return summary


def score_web_relevance(question: str, text: str) -> int:
    q_tokens = set(normalize(question))
    t_tokens = set(normalize(text))
    if not q_tokens or not t_tokens:
        return 0
    score = len(q_tokens.intersection(t_tokens))
    question_lower = (question or "").lower()
    text_lower = (text or "").lower()

    domain_pairs = [
        ("s4hana", "s4hana"),
        ("s/4hana", "s/4hana"),
        ("sap fico", "sap fico"),
        ("sap fico", "fico"),
        ("fico", "fico"),
        ("financial accounting", "financial accounting"),
        ("controlling", "controlling"),
    ]
    for q_term, t_term in domain_pairs:
        if q_term in question_lower and t_term in text_lower:
            score += 1
    return score


def fetch_web_answer(question: str, module: str) -> str | None:
    query = (question or "").strip()
    if not query:
        return None
    encoded_query = urllib.parse.quote(query)
    urls = [
        f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1&skip_disambig=1&kl=us-en",
        f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1&skip_disambig=1&ia=web",
    ]
    for url in urls:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=7) as response:
                data = json.loads(response.read().decode("utf-8", errors="ignore"))
            candidates = []
            abstract_text = (data.get("AbstractText") or "").strip()
            if abstract_text:
                candidates.append(abstract_text)
            related = data.get("RelatedTopics") or []
            for item in related:
                if isinstance(item, dict):
                    text = (item.get("Text") or "").strip()
                    if text:
                        candidates.append(text)
                elif isinstance(item, str) and item.strip():
                    candidates.append(item.strip())
            for candidate in candidates:
                cleaned = summarize_web_text(candidate)
                relevance = score_web_relevance(question, cleaned)
                question_lower = (question or "").lower()
                text_lower = (cleaned or "").lower()
                has_domain_match = (
                    ("s4hana" in question_lower and ("s/4hana" in text_lower or "s4hana" in text_lower or "hana" in text_lower))
                    or ("sap fico" in question_lower and ("sap fico" in text_lower or "fico" in text_lower or "financial accounting" in text_lower or "controlling" in text_lower))
                    or ("fico" in question_lower and ("fico" in text_lower or "financial accounting" in text_lower))
                )
                if relevance >= 1 or has_domain_match or len((question or "").split()) >= 4:
                    return cleaned
        except Exception:
            continue
    return None


def find_knowledge(question: str, requested_module: str) -> Tuple[dict | None, int]:
    question_lower = question.lower()
    tokens = set(normalize(question))
    best_item = None
    best_score = 0
    for item in KNOWLEDGE:
        score = 0
        for keyword in item.get("keywords", []):
            keyword_tokens = set(normalize(keyword))
            phrase_pattern = rf"(?<![a-z0-9]){re.escape(keyword.lower())}(?![a-z0-9])"
            if re.search(phrase_pattern, question_lower):
                score += 5 + len(keyword_tokens)
            else:
                score += len(tokens.intersection(keyword_tokens))
        if requested_module != "All" and requested_module in item.get("module", ""):
            score += 1
        if score > best_score:
            best_item, best_score = item, score
    return (best_item, best_score) if best_score >= 3 else (None, best_score)


def create_answer(question: str, context: dict) -> dict:
    item, score = find_knowledge(question, context.get("module", "All"))
    if not item:
        web_summary = fetch_web_answer(question, context.get("module", "All"))
        if web_summary:
            relevance = score_web_relevance(question, web_summary)
            question_lower = (question or "").lower()
            text_lower = (web_summary or "").lower()
            has_domain_match = (
                ("s4hana" in question_lower and ("s/4hana" in text_lower or "s4hana" in text_lower or "hana" in text_lower))
                or ("sap fico" in question_lower and ("sap fico" in text_lower or "fico" in text_lower or "financial accounting" in text_lower or "controlling" in text_lower))
                or ("fico" in question_lower and ("fico" in text_lower or "financial accounting" in text_lower))
            )
            if relevance >= 1 or has_domain_match or len((question or "").split()) >= 4:
                answer = (
                    f"{web_summary.strip()} For this SAP context, validate the recommendation against your product, release, and control design before using it in production."
                )
                return {
                    "matched": False,
                    "topic": "General web answer",
                    "module": context.get("module", "All"),
                    "confidence": min(88, 52 + relevance * 8 + (18 if has_domain_match else 0)),
                    "answer": answer,
                    "steps": [
                        "Review the general recommendation in the context of your SAP process and transaction flow.",
                        "Confirm the exact product, release, and scope before applying any design change.",
                        "Validate the final approach in a non-production system with business and controls owners.",
                    ],
                    "transactions": [],
                    "source": "General web answer",
                    "notice": "This is a general web answer from public sources and not a confirmed SAP configuration decision.",
                    "followups": [
                        "Which transaction code or SAP app are you using?",
                        "What exact error message or business outcome are you seeing?",
                        "Is this in ECC or S/4HANA and what is the release?",
                    ],
                }
        return {
            "matched": False,
            "topic": "Needs clarification",
            "module": context.get("module", "All"),
            "confidence": 20,
            "answer": "I could not find enough trusted local knowledge to answer this safely.",
            "steps": [],
            "transactions": [],
            "source": "No sufficiently relevant local source",
            "notice": "No answer was guessed. A SAP FICO specialist should review uncommon or configuration-specific issues.",
            "followups": [],
        }

    product_note = f"This guidance is framed for {context.get('product','')} {context.get('release','')}."
    country_note = (
        f" Country context: {context.get('country')}; confirm local tax and statutory requirements." if context.get("country") != "Global" else ""
    )
    confidence = min(94, 58 + score * 4)
    return {
        "matched": True,
        "topic": item.get("topic"),
        "module": item.get("module"),
        "confidence": confidence,
        "answer": f"{item.get('summary','')} {product_note}{country_note}",
        "steps": item.get("steps", []),
        "transactions": item.get("transactions", []),
        "source": item.get("source", ""),
        "notice": "Validate configuration and test in a non-production system before applying changes.",
        "followups": item.get("followups", []),
    }


def validate_question(payload: dict) -> Tuple[dict | None, list[str]]:
    errors = []
    question = str(payload.get("question", "")).strip()
    if len(question) < 8:
        errors.append("Question must contain at least 8 characters.")
    if len(question) > 1000:
        errors.append("Question must not exceed 1,000 characters.")

    allowed = {
        "module": {"All", "FI", "CO", "FI/CO"},
        "product": {"SAP S/4HANA", "SAP ECC"},
        "release": {"Current", "2023", "2022", "1909", "ECC 6.0"},
        "country": {"Global", "India", "United States", "United Kingdom", "Germany"},
    }
    context = {"question": question}
    for field, choices in allowed.items():
        value = str(payload.get(field, "")).strip()
        if value not in choices:
            errors.append(f"Select a valid {field}.")
        context[field] = value
    if context["product"] == "SAP ECC" and context["release"] != "ECC 6.0":
        errors.append("SAP ECC questions must use the ECC 6.0 release context.")
    if context["product"] == "SAP S/4HANA" and context["release"] == "ECC 6.0":
        errors.append("SAP S/4HANA cannot use the ECC 6.0 release context.")
    return (context if not errors else None), errors


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "time": utc_now()})


@app.route("/api/topics")
def topics():
    items = [{"topic": x.get("topic"), "module": x.get("module"), "transactions": x.get("transactions")} for x in KNOWLEDGE]
    return jsonify({"items": items})


@app.route("/api/conversations", methods=["GET"])
def conversations():
    with closing(connect()) as db:
        rows = db.execute(
            """SELECT c.*, f.rating FROM conversations c
               LEFT JOIN feedback f ON f.conversation_id = c.id
               ORDER BY c.created_at DESC LIMIT 50"""
        ).fetchall()
    return jsonify({"items": [dict(row) for row in rows]})


@app.route("/api/ask", methods=["POST"])
def ask():
    payload = request.get_json(force=True)
    context, errors = validate_question(payload)
    if errors:
        return jsonify({"error": "Please correct the highlighted information.", "details": errors}), 422
    result = create_answer(context["question"], context)
    conversation_id = str(uuid.uuid4())
    with closing(connect()) as db:
        db.execute(
            """INSERT INTO conversations
               (id, question, answer, topic, module, product, release_name, country, confidence, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                conversation_id,
                context["question"],
                result["answer"],
                result["topic"],
                result["module"],
                context["product"],
                context["release"],
                context["country"],
                result["confidence"],
                utc_now(),
            ),
        )
        db.commit()
    result["id"] = conversation_id
    return jsonify(result), 201


@app.route("/api/feedback", methods=["POST"])
def feedback():
    payload = request.get_json(force=True)
    conversation_id = str(payload.get("conversationId", "")).strip()
    rating = str(payload.get("rating", "")).strip()
    comment = str(payload.get("comment", "")).strip()
    if not conversation_id or rating not in {"helpful", "not_helpful"}:
        return jsonify({"error": "A valid conversation and rating are required."}), 422
    if len(comment) > 500:
        return jsonify({"error": "Feedback must not exceed 500 characters."}), 422
    with closing(connect()) as db:
        exists = db.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not exists:
            return jsonify({"error": "Conversation not found."}), 404
        db.execute(
            """INSERT INTO feedback (conversation_id, rating, comment, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(conversation_id) DO UPDATE SET rating=excluded.rating, comment=excluded.comment, created_at=excluded.created_at""",
            (conversation_id, rating, comment, utc_now()),
        )
        db.commit()
    return jsonify({"message": "Thank you. Your feedback has been saved."}), 201


@app.route("/api/dashboard")
def dashboard():
    with closing(connect()) as db:
        total = db.execute("SELECT COUNT(*) AS count FROM conversations").fetchone()["count"]
        helpful = db.execute("SELECT COUNT(*) AS count FROM feedback WHERE rating = 'helpful'").fetchone()["count"]
        topics = [dict(row) for row in db.execute(
            "SELECT topic, COUNT(*) AS count FROM conversations GROUP BY topic ORDER BY count DESC, topic LIMIT 5"
        )]
    return jsonify({"questions": total, "helpful": helpful, "knowledgeTopics": len(KNOWLEDGE), "topics": topics})


@app.route("/api/conversations/<conversation_id>", methods=["GET"])
def get_conversation(conversation_id: str):
    with closing(connect()) as db:
        row = db.execute(
            """SELECT c.*, f.rating, f.comment AS feedback_comment
               FROM conversations c
               LEFT JOIN feedback f ON f.conversation_id = c.id
               WHERE c.id = ?""",
            (conversation_id,),
        ).fetchone()
    if not row:
        return jsonify({"error": "Conversation not found."}), 404
    return jsonify(dict(row))


@app.route("/api/conversations/<conversation_id>", methods=["POST", "DELETE"])
def update_or_delete_conversation(conversation_id: str):
    payload = request.get_json(silent=True) or {}
    if request.method == "DELETE":
        with closing(connect()) as db:
            exists = db.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if not exists:
                return jsonify({"error": "Conversation not found."}), 404
            db.execute("DELETE FROM feedback WHERE conversation_id = ?", (conversation_id,))
            db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            db.commit()
        return jsonify({"message": "Conversation deleted."})

    action = str(payload.get("action", "")).strip()
    if action != "update":
        return jsonify({"error": "Unsupported action."}), 422

    question = str(payload.get("question", "")).strip()
    if len(question) < 8 or len(question) > 1000:
        return jsonify({"error": "Question must contain 8 to 1,000 characters."}), 422

    module = str(payload.get("module", "")).strip()
    product = str(payload.get("product", "")).strip()
    release = str(payload.get("release", "")).strip()
    country = str(payload.get("country", "")).strip()
    context, errors = validate_question({
        "question": question,
        "module": module,
        "product": product,
        "release": release,
        "country": country,
    })
    if errors:
        return jsonify({"error": "Please correct the highlighted information.", "details": errors}), 422

    result = create_answer(question, context)
    with closing(connect()) as db:
        exists = db.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not exists:
            return jsonify({"error": "Conversation not found."}), 404
        db.execute(
            """UPDATE conversations
               SET question = ?, answer = ?, topic = ?, module = ?, product = ?, release_name = ?, country = ?, confidence = ?
               WHERE id = ?""",
            (question, result["answer"], result["topic"], result["module"], product, release, country, result["confidence"], conversation_id),
        )
        db.commit()
    result["id"] = conversation_id
    return jsonify(result)


@app.route("/api/feedback/<conversation_id>", methods=["PUT", "DELETE"])
def update_or_delete_feedback(conversation_id: str):
    payload = request.get_json(silent=True) or {}
    if request.method == "DELETE":
        with closing(connect()) as db:
            db.execute("DELETE FROM feedback WHERE conversation_id = ?", (conversation_id,))
            db.commit()
        return jsonify({"message": "Feedback deleted."})

    rating = str(payload.get("rating", "")).strip()
    comment = str(payload.get("comment", "")).strip()
    if rating not in {"helpful", "not_helpful"}:
        return jsonify({"error": "A valid feedback rating is required."}), 422
    if len(comment) > 500:
        return jsonify({"error": "Feedback must not exceed 500 characters."}), 422

    with closing(connect()) as db:
        exists = db.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not exists:
            return jsonify({"error": "Conversation not found."}), 404
        db.execute(
            """INSERT INTO feedback (conversation_id, rating, comment, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(conversation_id) DO UPDATE SET rating=excluded.rating, comment=excluded.comment, created_at=excluded.created_at""",
            (conversation_id, rating, comment, utc_now()),
        )
        db.commit()
    return jsonify({"message": "Feedback updated."})


@app.route("/")
@app.route("/<path:relpath>")
def serve(relpath: str = "index.html"):
    requested = relpath or "index.html"
    if (STATIC_DIR / requested).is_file():
        return send_from_directory(str(STATIC_DIR), requested)
    return send_from_directory(str(STATIC_DIR), "index.html")


if __name__ == "__main__":
    initialize_database()
    app.run(host="0.0.0.0", port=8000)
