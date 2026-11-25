"""Stateless, rule-based document Q&A website.

The selected document is sent with each question and processed in memory. The
application does not write documents or knowledge bases to disk or a database.
DOCX is the primary input; UTF-8 TXT and CSV are also accepted.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any, Iterable

from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from flask import Flask, abort, jsonify, render_template, request, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"
ALLOWED_EXTENSIONS = {"docx", "txt", "csv"}
# Vercel's ordinary Function request-body limit is 4.5 MB. Leave room for the
# multipart form fields and headers by limiting the document itself to 4 MiB.
MAX_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_QUESTION_CHARS = 500
MAX_RESULTS = 3

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES + 64 * 1024


def iter_docx_blocks(document: Document) -> Iterable[Paragraph | Table]:
    """Yield DOCX paragraphs and tables in document order."""
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def clean_text(value: str) -> str:
    return " ".join((value or "").split())


def make_passage(text: str, source: str, kind: str, data: dict[str, str] | None = None) -> dict[str, Any] | None:
    text = clean_text(text)
    if not text:
        return None
    return {"text": text, "source": source, "kind": kind, "structured_data": data or {}}


def parse_docx(file_bytes: bytes) -> list[dict[str, Any]]:
    """Extract text passages and simple header/value facts from DOCX tables."""
    document = Document(io.BytesIO(file_bytes))
    passages: list[dict[str, Any]] = []
    current_heading = "Document"
    paragraph_number = 0
    table_number = 0

    for block in iter_docx_blocks(document):
        if isinstance(block, Paragraph):
            text = clean_text(block.text)
            if not text:
                continue
            paragraph_number += 1
            style_name = getattr(block.style, "name", "") or ""
            kind = "heading" if style_name.lower().startswith("heading") else "paragraph"
            if kind == "heading":
                current_heading = text
            source = f"Paragraph {paragraph_number}"
            if current_heading != "Document":
                source += f" · {current_heading}"
            passage = make_passage(text, source, kind)
            if passage:
                passages.append(passage)
            continue

        table_number += 1
        rows = [[clean_text(cell.text) for cell in row.cells] for row in block.rows]
        rows = [row for row in rows if any(row)]
        if not rows:
            continue
        headers = rows[0]
        has_headers = bool(headers) and all(headers)
        data_rows = rows[1:] if has_headers and len(rows) > 1 else rows
        for row_number, row in enumerate(data_rows, start=2 if has_headers else 1):
            mapping = {
                header: row[index]
                for index, header in enumerate(headers[:len(row)])
                if has_headers and header and row[index]
            }
            text = " | ".join(f"{key}: {value}" for key, value in mapping.items())
            if not text:
                text = " | ".join(value for value in row if value)
            source = f"Table {table_number}, row {row_number}"
            if current_heading != "Document":
                source += f" · {current_heading}"
            passage = make_passage(text, source, "table", mapping)
            if passage:
                passages.append(passage)
    return passages


def parse_txt(file_bytes: bytes) -> list[dict[str, Any]]:
    text = file_bytes.decode("utf-8-sig")
    passages = []
    for number, paragraph in enumerate(re.split(r"\n\s*\n", text), start=1):
        passage = make_passage(paragraph, f"Paragraph {number}", "paragraph")
        if passage:
            passages.append(passage)
    return passages


def parse_csv(file_bytes: bytes) -> list[dict[str, Any]]:
    text = file_bytes.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows:
        return []
    headers = [clean_text(value) for value in rows[0]]
    passages = []
    for row_number, row in enumerate(rows[1:], start=2):
        values = [clean_text(value) for value in row]
        mapping = {
            headers[index]: values[index]
            for index in range(min(len(headers), len(values)))
            if headers[index] and values[index]
        }
        text = " | ".join(f"{key}: {value}" for key, value in mapping.items())
        if not text:
            text = " | ".join(value for value in values if value)
        passage = make_passage(text, f"CSV row {row_number}", "table", mapping)
        if passage:
            passages.append(passage)
    return passages


def extract_knowledge(file_bytes: bytes, extension: str) -> list[dict[str, Any]]:
    if extension == "docx":
        return parse_docx(file_bytes)
    if extension == "txt":
        return parse_txt(file_bytes)
    if extension == "csv":
        return parse_csv(file_bytes)
    raise ValueError("Unsupported document type")


# Fixed question openings and exact-term matching only: no NLP package,
# stemming, embeddings, semantic search, language model, or RAG.
QUESTION_PREFIXES = (
    "how many", "how much", "what is", "what are", "what was", "what were",
    "who is", "who are", "who was", "who were", "when is", "when was",
    "when were", "where is", "where are", "where was", "where were",
    "why is", "why are", "why was", "why were", "tell me", "which",
    "who", "when", "where", "why", "what", "list", "give",
)
CONNECTOR_WORDS = {
    "a", "an", "and", "are", "at", "be", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "the", "to", "was", "were", "with",
}
WORD_PATTERN = re.compile(r"[a-z0-9]+(?:[._'-][a-z0-9]+)*", re.IGNORECASE)
DATE_OR_NUMBER = re.compile(r"\b(?:\d{1,4}(?:[-/.]\d{1,2}){1,2}|\d+(?:\.\d+)?)\b")


def prepare_question(question: str) -> tuple[list[str], str]:
    cleaned = " ".join(question.casefold().split()).strip(" ?!.\t\r\n")
    intent = "general"
    if cleaned.startswith(("how many", "how much")):
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
    return list(dict.fromkeys(words)), intent


def search_knowledge(passages: list[dict[str, Any]], question: str) -> tuple[list[dict[str, Any]], str | None]:
    terms, intent = prepare_question(question)
    if not terms:
        return [], "Add a specific name, topic, or term from the document to your question."

    ranked = []
    for passage in passages:
        passage_words = set(WORD_PATTERN.findall(passage["text"].casefold()))
        matched = [term for term in terms if term in passage_words]
        if not matched:
            continue
        overlap = len(matched) / len(terms)
        phrase = " ".join(terms)
        exact_phrase = phrase in " ".join(passage["text"].casefold().split())
        score = overlap + (0.35 if phrase and exact_phrase else 0.0)
        if intent in {"numeric", "time"} and DATE_OR_NUMBER.search(passage["text"]):
            score += 0.15
        ranked.append({
            "text": passage["text"],
            "source": passage["source"],
            "kind": passage["kind"],
            "matched_terms": matched,
            "score": round(score, 3),
        })

    ranked.sort(key=lambda item: (item["score"], len(item["matched_terms"])), reverse=True)
    minimum_score = 0.35 if len(terms) == 1 else 0.34
    ranked = [item for item in ranked if item["score"] >= minimum_score]
    return ranked[:MAX_RESULTS], None


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/style.css")
def stylesheet():
    return send_from_directory(PUBLIC_DIR, "style.css")


@app.get("/app.js")
def javascript():
    return send_from_directory(PUBLIC_DIR, "app.js")


@app.get("/sample.txt")
def sample_document():
    return send_from_directory(PUBLIC_DIR, "sample.txt", mimetype="text/plain")


@app.post("/ask")
def ask():
    uploaded = request.files.get("document")
    question = " ".join(request.form.get("question", "").split())
    if uploaded is None or not uploaded.filename:
        return jsonify(error="Choose a document or load the sample file first."), 400
    if not question:
        return jsonify(error="Enter a question first."), 400
    if len(question) > MAX_QUESTION_CHARS:
        return jsonify(error=f"Keep the question under {MAX_QUESTION_CHARS} characters."), 400

    filename = secure_filename(uploaded.filename)
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        return jsonify(error="Use a DOCX, TXT, or CSV file."), 400
    file_bytes = uploaded.read(MAX_UPLOAD_BYTES + 1)
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        return jsonify(error="The document exceeds the 4 MiB file limit."), 413
    if not file_bytes:
        return jsonify(error="The selected document is empty."), 400

    try:
        passages = extract_knowledge(file_bytes, extension)
    except Exception as error:
        app.logger.info("Document parsing failed: %s", error)
        return jsonify(error="Could not read this file. Check that it is a valid DOCX, UTF-8 TXT, or CSV."), 400
    if not passages:
        return jsonify(error="No readable text was found in the document."), 400

    results, message = search_knowledge(passages, question)
    return jsonify(
        filename=filename,
        passage_count=len(passages),
        results=results,
        message=message,
        answer_found=bool(results),
    )


@app.errorhandler(RequestEntityTooLarge)
def request_too_large(_error):
    return jsonify(error="The request is too large. Use a document smaller than 4 MiB."), 413


@app.errorhandler(413)
def payload_too_large(_error):
    return jsonify(error="The request is too large. Use a document smaller than 4 MiB."), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
