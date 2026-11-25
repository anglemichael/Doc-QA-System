"""Local, rule-based document question-answering website.

Supported inputs: DOCX (primary), TXT, and CSV. The application uses exact
lexical matching and deterministic rules; it does not use NLP libraries,
embeddings, a language model, or RAG.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from flask import Flask, abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
DB_PATH = INSTANCE_DIR / "knowledge_base.sqlite3"
DATABASE_URL = os.environ.get("DATABASE_URL")
ALLOWED_EXTENSIONS = {"docx", "txt", "csv"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_QUESTION_CHARS = 500
MAX_RESULTS = 3

app = Flask(__name__, static_folder=None)
app.config.update(
    SECRET_KEY=os.environ.get("DOCUMENT_QA_SECRET", secrets.token_hex(32)),
    MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


class DatabaseAdapter:
    """Small DB-API adapter for local SQLite and hosted PostgreSQL."""

    def __init__(self, connection: Any, postgres: bool):
        self.connection = connection
        self.postgres = postgres

    def _sql(self, statement: str) -> str:
        return statement.replace("?", "%s") if self.postgres else statement

    def execute(self, statement: str, parameters: tuple[Any, ...] = ()):
        return self.connection.execute(self._sql(statement), parameters)

    def executemany(self, statement: str, parameters: Iterable[tuple[Any, ...]]):
        return self.connection.executemany(self._sql(statement), parameters)


def get_db() -> tuple[Any, bool]:
    """Use PostgreSQL when DATABASE_URL is configured; otherwise use local SQLite."""
    if DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(DATABASE_URL, row_factory=dict_row), True
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection, False


@contextmanager
def db_session() -> Iterable[Any]:
    """Commit successful work and always close the database connection."""
    connection, postgres = get_db()
    try:
        if postgres:
            with connection.transaction():
                yield DatabaseAdapter(connection, postgres=True)
        else:
            with connection:
                yield DatabaseAdapter(connection, postgres=False)
    finally:
        connection.close()


_db_initialized = False


def init_db() -> None:
    global _db_initialized
    if _db_initialized:
        return
    with db_session() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        id_column = "BIGSERIAL PRIMARY KEY" if DATABASE_URL else "INTEGER PRIMARY KEY AUTOINCREMENT"
        db.execute(
            f"""CREATE TABLE IF NOT EXISTS knowledge_units (
                id {id_column},
                document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                text TEXT NOT NULL,
                source TEXT NOT NULL,
                kind TEXT NOT NULL,
                structured_data TEXT NOT NULL DEFAULT '{{}}'
            )"""
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_units_document ON knowledge_units(document_id)")
    _db_initialized = True


@app.before_request
def ensure_database_ready() -> None:
    if os.environ.get("VERCEL") and not DATABASE_URL:
        raise RuntimeError("Set DATABASE_URL to a persistent PostgreSQL database before deploying to Vercel.")
    if os.environ.get("VERCEL") and not os.environ.get("DOCUMENT_QA_SECRET"):
        raise RuntimeError("Set DOCUMENT_QA_SECRET in the Vercel project settings.")
    init_db()


@app.get("/style.css")
def stylesheet():
    """Serve Vercel's public asset locally; Vercel serves public/ via its CDN."""
    return send_from_directory(BASE_DIR / "public", "style.css")


def iter_docx_blocks(document: Document) -> Iterable[Paragraph | Table]:
    """Yield DOCX paragraphs and tables in their original document order."""
    body = document.element.body
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def clean_cell(value: str) -> str:
    return " ".join((value or "").split())


def make_unit(text: str, source: str, kind: str, data: dict[str, Any] | None = None) -> dict[str, Any] | None:
    text = clean_cell(text)
    if not text:
        return None
    return {
        "text": text,
        "source": source,
        "kind": kind,
        "structured_data": data or {},
    }


def parse_docx(file_bytes: bytes) -> list[dict[str, Any]]:
    """Build evidence units from DOCX paragraphs and tables.

    Table rows are also represented as explicit header/value mappings when
    the first row contains headers. This preserves simple facts for lookup.
    """
    document = Document(io.BytesIO(file_bytes))
    units: list[dict[str, Any]] = []
    current_heading = "Document"
    paragraph_number = 0
    table_number = 0

    for block in iter_docx_blocks(document):
        if isinstance(block, Paragraph):
            text = clean_cell(block.text)
            if not text:
                continue
            paragraph_number += 1
            style_name = getattr(block.style, "name", "") or ""
            if style_name.lower().startswith("heading"):
                current_heading = text
                kind = "heading"
            else:
                kind = "paragraph"
            unit = make_unit(
                text,
                f"Paragraph {paragraph_number}" + (f" · {current_heading}" if current_heading != "Document" else ""),
                kind,
            )
            if unit:
                units.append(unit)
            continue

        table_number += 1
        rows = [[clean_cell(cell.text) for cell in row.cells] for row in block.rows]
        rows = [row for row in rows if any(row)]
        if not rows:
            continue
        headers = rows[0]
        has_headers = len(headers) > 0 and all(headers)
        data_rows = rows[1:] if has_headers and len(rows) > 1 else rows
        for row_number, row in enumerate(data_rows, start=2 if has_headers else 1):
            mapping: dict[str, str] = {}
            if has_headers:
                mapping = {
                    header: row[index]
                    for index, header in enumerate(headers[: len(row)])
                    if header and index < len(row) and row[index]
                }
            row_text = " | ".join(f"{key}: {value}" for key, value in mapping.items())
            if not row_text:
                row_text = " | ".join(value for value in row if value)
            source = f"Table {table_number}, row {row_number}"
            if current_heading != "Document":
                source += f" · {current_heading}"
            unit = make_unit(row_text, source, "table", mapping)
            if unit:
                units.append(unit)

    return units


def parse_txt(file_bytes: bytes) -> list[dict[str, Any]]:
    text = file_bytes.decode("utf-8-sig")
    units: list[dict[str, Any]] = []
    for number, paragraph in enumerate(re.split(r"\n\s*\n", text), start=1):
        unit = make_unit(paragraph, f"Paragraph {number}", "paragraph")
        if unit:
            units.append(unit)
    return units


def parse_csv(file_bytes: bytes) -> list[dict[str, Any]]:
    text = file_bytes.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text, newline=""))
    rows = list(reader)
    if not rows:
        return []
    headers = [clean_cell(item) for item in rows[0]]
    units: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows[1:], start=2):
        values = [clean_cell(item) for item in row]
        mapping = {
            headers[index]: values[index]
            for index in range(min(len(headers), len(values)))
            if headers[index] and values[index]
        }
        row_text = " | ".join(f"{key}: {value}" for key, value in mapping.items())
        if not row_text:
            row_text = " | ".join(value for value in values if value)
        unit = make_unit(row_text, f"CSV row {row_number}", "table", mapping)
        if unit:
            units.append(unit)
    return units


def extract_knowledge(file_bytes: bytes, extension: str) -> list[dict[str, Any]]:
    if extension == "docx":
        return parse_docx(file_bytes)
    if extension == "txt":
        return parse_txt(file_bytes)
    if extension == "csv":
        return parse_csv(file_bytes)
    raise ValueError("This file type is not supported.")


# Only fixed question-opening phrases and connector words are removed. The
# remaining words are searched literally: no stemming, synonyms, or semantics.
QUESTION_PREFIXES = (
    "how many", "how much", "what is", "what are", "what was", "what were",
    "who is", "who are", "who was", "who were", "when is", "when was",
    "when were", "where is", "where are", "where was", "where were",
    "why is", "why are", "why was", "why were", "which", "who", "when",
    "where", "why", "what", "list", "give", "tell me",
)
CONNECTOR_WORDS = {"a", "an", "and", "are", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or", "the", "to", "was", "were", "with"}
WORD_PATTERN = re.compile(r"[a-z0-9]+(?:[._'-][a-z0-9]+)*", re.IGNORECASE)
DATE_OR_NUMBER = re.compile(r"\b(?:\d{1,4}(?:[-/.]\d{1,2}){1,2}|\d+(?:\.\d+)?)\b")


def prepare_question(question: str) -> tuple[list[str], str]:
    cleaned = " ".join(question.casefold().split()).strip(" ?!.\t\r\n")
    intent = "general"
    if cleaned.startswith("how many") or cleaned.startswith("how much"):
        intent = "numeric"
    elif cleaned.startswith("when"):
        intent = "time"
    for prefix in QUESTION_PREFIXES:
        if cleaned == prefix:
            cleaned = ""
            break
        if cleaned.startswith(prefix + " "):
            cleaned = cleaned[len(prefix):].strip()
            break
    words = [word for word in WORD_PATTERN.findall(cleaned) if word not in CONNECTOR_WORDS]
    # Keep first occurrence order while removing duplicates.
    return list(dict.fromkeys(words)), intent


def search_knowledge(document_id: str, question: str) -> tuple[list[dict[str, Any]], str | None]:
    terms, intent = prepare_question(question)
    if not terms:
        return [], "Please include at least one specific name, topic, or term from the document."

    with db_session() as db:
        rows = db.execute(
            "SELECT id, text, source, kind, structured_data FROM knowledge_units WHERE document_id = ?",
            (document_id,),
        ).fetchall()

    ranked: list[dict[str, Any]] = []
    for row in rows:
        passage = row["text"]
        passage_words = set(WORD_PATTERN.findall(passage.casefold()))
        matched = [term for term in terms if term in passage_words]
        if not matched:
            continue
        # Transparent lexical score: overlap fraction plus a literal phrase bonus.
        overlap = len(matched) / len(terms)
        normalized_text = " ".join(passage.casefold().split())
        phrase = " ".join(terms)
        score = overlap + (0.35 if phrase and phrase in normalized_text else 0.0)
        if intent in {"numeric", "time"} and DATE_OR_NUMBER.search(passage):
            score += 0.15
        ranked.append({
            "id": row["id"],
            "text": passage,
            "source": row["source"],
            "kind": row["kind"],
            "structured_data": json.loads(row["structured_data"]),
            "matched_terms": matched,
            "score": score,
        })

    ranked.sort(key=lambda item: (item["score"], len(item["matched_terms"])), reverse=True)
    # Require a useful term overlap; otherwise the system abstains.
    minimum_score = 0.35 if len(terms) == 1 else 0.34
    ranked = [item for item in ranked if item["score"] >= minimum_score]
    if not ranked:
        return [], None
    return ranked[:MAX_RESULTS], None


def get_document(document_id: str) -> sqlite3.Row | None:
    with db_session() as db:
        return db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()


def get_unit_count(document_id: str) -> int:
    with db_session() as db:
        result = db.execute(
            "SELECT COUNT(*) AS count FROM knowledge_units WHERE document_id = ?", (document_id,)
        ).fetchone()
    return int(result["count"])


def save_document(filename: str, extension: str, units: list[dict[str, Any]]) -> str:
    document_id = uuid.uuid4().hex
    with db_session() as db:
        db.execute(
            "INSERT INTO documents(id, filename, file_type, created_at) VALUES (?, ?, ?, ?)",
            (document_id, filename, extension, datetime.now(timezone.utc).isoformat()),
        )
        db.executemany(
            "INSERT INTO knowledge_units(document_id, text, source, kind, structured_data) VALUES (?, ?, ?, ?, ?)",
            [
                (document_id, unit["text"], unit["source"], unit["kind"], json.dumps(unit["structured_data"], ensure_ascii=False))
                for unit in units
            ],
        )
    return document_id


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        uploaded = request.files.get("document")
        if uploaded is None or not uploaded.filename:
            flash("Choose a DOCX, TXT, or CSV file first.", "error")
            return redirect(url_for("index"))

        safe_name = secure_filename(uploaded.filename)
        extension = Path(safe_name).suffix.lower().lstrip(".")
        if extension not in ALLOWED_EXTENSIONS:
            flash("Unsupported file. Upload a DOCX, TXT, or CSV file.", "error")
            return redirect(url_for("index"))

        file_bytes = uploaded.read(MAX_UPLOAD_BYTES + 1)
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            flash("The file is larger than the 10 MB limit.", "error")
            return redirect(url_for("index"))
        if not file_bytes:
            flash("The selected file is empty.", "error")
            return redirect(url_for("index"))

        try:
            units = extract_knowledge(file_bytes, extension)
        except Exception as error:
            # Parser errors are shown as a safe, helpful message; details stay in server logs.
            app.logger.warning("Could not process uploaded document: %s", error)
            flash("The file could not be read. Check that it is a valid DOCX, UTF-8 TXT, or CSV file.", "error")
            return redirect(url_for("index"))
        if not units:
            flash("No readable text was found in that document.", "error")
            return redirect(url_for("index"))

        # Replace the current session's document to keep this demo simple.
        old_id = session.get("document_id")
        if old_id:
            with db_session() as db:
                db.execute("DELETE FROM documents WHERE id = ?", (old_id,))
        document_id = save_document(safe_name, extension, units)
        session["document_id"] = document_id
        session.pop("last_question", None)
        flash(f"Knowledge base created from {len(units)} document passages and table rows.", "success")
        return redirect(url_for("index"))

    document_id = session.get("document_id")
    document = get_document(document_id) if document_id else None
    if document is None:
        session.pop("document_id", None)
        document_id = None
    last_question = session.get("last_question", "")
    results: list[dict[str, Any]] = []
    if document is not None and last_question:
        results, _message = search_knowledge(document["id"], last_question)
    return render_template(
        "index.html",
        document=document,
        unit_count=get_unit_count(document_id) if document_id else 0,
        results=results,
        last_question=last_question,
    )


@app.post("/ask")
def ask():
    document_id = session.get("document_id")
    if not document_id or not get_document(document_id):
        flash("Upload a document before asking a question.", "error")
        return redirect(url_for("index"))
    question = " ".join(request.form.get("question", "").split())
    if not question:
        flash("Enter a question first.", "error")
        return redirect(url_for("index"))
    if len(question) > MAX_QUESTION_CHARS:
        flash(f"Keep the question under {MAX_QUESTION_CHARS} characters.", "error")
        return redirect(url_for("index"))

    _results, message = search_knowledge(document_id, question)
    session["last_question"] = question
    if message:
        flash(message, "error")
    return redirect(url_for("index"))


@app.post("/clear")
def clear_document():
    document_id = session.pop("document_id", None)
    session.pop("last_question", None)
    if document_id:
        with db_session() as db:
            db.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    flash("The current document and its knowledge base were cleared.", "success")
    return redirect(url_for("index"))


@app.errorhandler(RequestEntityTooLarge)
def too_large(_error):
    flash("The file is larger than the 10 MB limit.", "error")
    return redirect(url_for("index"))


@app.errorhandler(413)
def payload_too_large(_error):
    return too_large(_error)


if __name__ == "__main__":
    init_db()
    # Local demonstration server only. Keep it bound to this computer.
    app.run(host="127.0.0.1", port=5000, debug=False)
