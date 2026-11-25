# Rule-Based Document Question Answering Website

A Flask website for asking questions about a document. **DOCX is the primary format**; UTF-8 TXT and CSV are also supported. It uses local SQLite during local development and PostgreSQL when `DATABASE_URL` is configured for deployment.

## Assignment constraints

This project uses a symbolic, rule-based approach. It does not use NLP packages, language models, embeddings, semantic search, or RAG. It removes a small set of fixed question openings, compares exact terms against source passages, and returns the best matching evidence. Every result includes the passage's source location. If there is not enough literal overlap, it abstains.

DOCX paragraphs and headings are stored as evidence passages. DOCX tables are converted into rows of `column: value` pairs and kept with their source table and row. CSV is represented the same way. TXT files are divided at blank lines. This is the system's knowledge base.

## Requirements

- Python 3.10 or newer
- `pip`
- A modern web browser

## Setup on Windows PowerShell

Open PowerShell in this folder, then run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

If PowerShell blocks virtual-environment activation, use Command Prompt instead:

```bat
py -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000> in a browser. Stop the server with `Ctrl+C` in the terminal.

## Setup on macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Then open <http://127.0.0.1:5000>.

## How to use

1. Choose a `.docx`, `.txt`, or `.csv` document and select **Upload and process**.
2. The app extracts passages, headings, and table rows and stores them in SQLite locally or PostgreSQL in a deployment.
3. Enter a question using key terms or names as they appear in the document.
4. Review the matching passage and its paragraph, table-row, or CSV-row reference.
5. Select **Clear document** to delete the current document's extracted knowledge.

The upload limit is 10 MB. DOCX is the main supported format. TXT must be UTF-8. CSV uses the first row as column headings. PDF, scanned images, legacy `.doc`, and other formats are not supported by this project version.

## Answer method

The question handler recognizes a short list of fixed question openings, such as `what is`, `when`, and `how many`, then searches the remaining exact terms. A passage's score is based on the fraction of question terms found in that passage, with a small bonus for an exact phrase match. For time and quantity questions, a simple rule slightly favors passages containing numeric or date-like text. The score is a search heuristic, not a probability or confidence estimate.

Answers are evidence passages, not AI-generated paraphrases. Exact-word search can miss a correct passage when the user uses synonyms or different wording. It may also return an irrelevant passage if the document repeats the same terms; users should inspect the displayed source.

## Data and privacy

Uploaded originals are read into memory and are not saved as uploaded files. Extracted knowledge units are stored in `instance/knowledge_base.sqlite3` locally or in the configured PostgreSQL database when deployed. Clearing the current document removes its database entries. Deployed use stores extracted document text in the hosted database, so only upload documents that you are allowed to store there. This is a classroom demonstration; review the security and privacy limits before sharing it publicly.

## Files

- `app.py` — Flask routes, file parsing, SQLite knowledge base, rule-based search, and answer selection.
- `templates/index.html` — upload, question, answer, and evidence interface.
- `public/style.css` — page styling; Vercel serves files in `public/` as static assets.
- `requirements.txt` — Python dependencies.
- `instance/knowledge_base.sqlite3` — created automatically for local use; not committed to Git.
- `.gitignore` — excludes local virtual environments, database data, and environment files.
- `DEPLOYMENT.md` — GitHub and Vercel deployment walkthrough.

## Evaluation suggestion for the assignment report

Prepare answerable and unanswerable questions for several sample DOCX files, including questions whose evidence is in prose and in tables. Record the expected passage and source for each question. Report answer accuracy, evidence correctness, source-location correctness, unsupported-answer rate, and document-processing success. Include failures caused by different wording or repeated terms, since these show the limits of exact matching.
