# Rule-Based Document Question Answering Website

A small Flask website for asking questions about a document. **DOCX is the primary format**; UTF-8 TXT and CSV are also supported. It uses fixed rules and exact-term search. It does not use NLP libraries, embeddings, a language model, or RAG.

## No database or backend storage

This demo does not save uploaded files or extracted text. The selected file stays in the browser tab. Each question sends that file to the Python server, which extracts passages, searches them in memory, returns matching evidence, and discards the request data after processing. Because there is no saved session, reselect or reload the file after refreshing the page.

This design suits a small examiner demo and avoids a database. It rebuilds the knowledge base for every question and sends the document to the hosted app each time. Do not upload a private document unless you are comfortable sending it to the hosting service. The upload limit is 4 MiB per file.

## Supported files

- `.docx` — paragraphs, headings, and tables.
- `.txt` — UTF-8 text separated into passages at blank lines.
- `.csv` — first row used for column headings; each later row becomes a knowledge unit.

Scanned PDFs, legacy `.doc`, and other file types are not supported.

## Run locally

Requirements: Python 3.12 or newer and `pip`.

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000> in a browser. Stop the server with `Ctrl+C`.

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

## Demonstrate with the included sample

1. Open the website.
2. Select **Use sample TXT document**.
3. Ask: `Who coordinates the campus garden project?`
4. The website should show the matching passage with **Asha Rao** and its paragraph citation.
5. Try `Where is the garden located?` or `How much is the project budget?`.
6. Try a question absent from the sample, such as `What is the principal's office phone number?`; the app should report no matching evidence.

The same sample file is available at `public/sample.txt` and is served to the browser from `/sample.txt`.

## How answers are selected

The system recognizes a short fixed list of question openings, removes a small list of connector words, and compares the remaining exact terms to each passage. Matching passages are ranked by exact-term overlap, with a small phrase-match bonus. A simple rule slightly favors passages containing numbers for `how many` and date-like questions. The score is a search heuristic, not a probability.

Answers are the source passages themselves, not newly generated paraphrases. Synonyms or substantially different wording may fail to match. The interface includes source labels so the examiner can inspect the evidence.

## Main files

- `app.py` — Flask routes, document parsers, in-memory knowledge base, and rule-based search.
- `templates/index.html` — upload, sample, question, and answer interface.
- `public/app.js` — keeps the selected file in the browser tab and sends it with each question.
- `public/style.css` — styling.
- `public/sample.txt` — examiner demonstration document.
- `requirements.txt` — Flask and DOCX parser dependencies.
- `DEPLOYMENT.md` — instructions for pushing the existing repository update and deploying on Vercel.

## Evaluation for the assignment report

Use the included sample to demonstrate answerable and unanswerable questions. For broader evaluation, prepare several short DOCX files with both prose and tables. Record each expected answer and source passage, then report answer accuracy, evidence correctness, source-location correctness, unsupported-answer rate, and document-processing success. Discuss exact-word matching failures as a system limitation.
