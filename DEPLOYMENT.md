# Publish the repository and deploy with Vercel

This walkthrough publishes the project to your personal GitHub account and connects that repository to Vercel. Keep the repository private while you review it, unless your instructor specifically asks for a public repository.

## Why the deployment uses PostgreSQL

The app uses SQLite on your computer. Vercel runs Flask as a serverless Python Function. Its file system is read-only except for temporary `/tmp` storage, so a SQLite database written by the app is not reliable persistent storage there. In production the app reads `DATABASE_URL` and uses PostgreSQL; locally, without that variable, it keeps using SQLite. The code requires both `DATABASE_URL` and `DOCUMENT_QA_SECRET` in Vercel rather than silently starting with temporary storage.

The PostgreSQL database stores extracted passages and table rows, not the original uploaded files. When a user clicks **Clear document**, the associated knowledge-base records are deleted. Vercel and the database provider will still process information needed to run the site, so do not upload private or sensitive documents unless you have permission to store them there.

## Part A — Prepare the project

1. Open the project folder, `document_qa_website`.
2. Check that it contains `app.py`, `templates/`, `public/`, `requirements.txt`, `README.md`, and this guide.
3. `.gitignore` excludes `.venv/`, `instance/`, and `.env` files. Do not remove those rules. They prevent local environments, the local SQLite database, and secrets from being uploaded.
4. Do not put a real database URL or secret in `app.py`, `README.md`, `.env.example`, or any other tracked file. `.env.example` is only a blank template.
5. The project expects a PostgreSQL connection string in the environment variable named `DATABASE_URL` and a long random session key in `DOCUMENT_QA_SECRET`.

## Part B — Create the GitHub repository

1. Sign in to your personal GitHub account.
2. Use **New repository** and choose a name such as `document-question-answering-system`.
3. Choose **Private** to start. You can later add your instructor as a collaborator or change visibility if the course requires it.
4. Do not select the options to create a README, `.gitignore`, or license on GitHub. The project already has files to push, and initializing the remote with extra files can create an avoidable merge conflict.
5. Create the empty repository and copy its HTTPS address, which will look like `https://github.com/YOUR-USERNAME/document-question-answering-system.git`.

GitHub's instructions explain how to create a personal repository and advise against initializing it with files when you are pushing an existing local project. [GitHub: Creating a new repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)

## Part C — Push the local project

Open PowerShell in the project folder. Use the full path below, adjusted only if you moved the folder:

```powershell
Set-Location "C:\Users\angel\Documents\Codex\2026-11-25\t\outputs\document_qa_website"
git init -b main
git add .
git status --short
```

Before committing, inspect the `git status` list. It should include source files and documentation. It must not include `.venv`, `instance`, a `.env` file, passwords, database URLs, or the assignment document. If any of those appear, stop and correct `.gitignore` before continuing.

Then make the first commit and connect the empty GitHub repository:

```powershell
git commit -m "Add rule-based document QA website"
git remote add origin https://github.com/YOUR-USERNAME/document-question-answering-system.git
git push -u origin main
```

Replace `YOUR-USERNAME` and the repository name with the exact values you chose. Git may open a browser sign-in window. Sign in there; do not paste a password or access token into the source code or this chat. If Git says the remote already exists, inspect it with `git remote -v` before changing anything.

After the push, reload the GitHub repository page and confirm that `app.py`, `templates/`, `public/`, `requirements.txt`, and `README.md` are present. Confirm that `.venv/`, `instance/`, and `.env` are absent.

## Part D — Create persistent PostgreSQL storage

1. Sign in to Vercel using the same GitHub account that owns the repository.
2. In Vercel Marketplace, choose a PostgreSQL provider such as Neon and create a database. Vercel's current storage setup uses Marketplace providers for Postgres; the old Vercel Postgres product is no longer the path for a new database.
3. Choose a region close to the Vercel Function region if the provider asks. Use the provider's pooled/serverless connection string if it offers one.
4. Copy the database connection string privately. It is a credential. Do not commit it, put it in a README, or share it in a screenshot.
5. In Vercel Project Settings → Environment Variables, create `DATABASE_URL` with that connection string for **Production**. Add a separate development/preview database URL for Preview deployments if you plan to use preview branches. Do not use production documents for previews.

Vercel Marketplace integrations can provision Postgres and add credentials as environment variables. Match the variable name to the name the app reads: `DATABASE_URL`. [Vercel: Storage on the Marketplace](https://vercel.com/docs/marketplace-storage), [Vercel: Postgres](https://vercel.com/docs/postgres)

## Part E — Add a persistent session secret

Create a random secret locally in PowerShell:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output directly into Vercel Project Settings → Environment Variables as `DOCUMENT_QA_SECRET`. Set it for Production and Preview. Use separate values for those environments if you configure them separately. Do not commit this value. Setting it makes Flask's signed session cookies stable across serverless instances and restarts.

After adding or changing environment variables, create a new deployment so the function receives them.

## Part F — Import and deploy the repository

1. In Vercel, select **Add New → Project**.
2. Connect GitHub if prompted and grant Vercel access to this repository. For a private personal repository, select the repository owner account and authorize the repo when asked.
3. Import `document-question-answering-system`.
4. Set the **Root Directory** to the repository root (`./`).
5. Let Vercel detect the Flask app. This project exports a Flask `app` from root `app.py` and includes dependencies in `requirements.txt`; leave Build Command and Output Directory at their detected defaults.
6. Confirm the Production environment has `DATABASE_URL` and `DOCUMENT_QA_SECRET`, then deploy.
7. Wait for the build to finish, open the generated deployment URL, and try the app.

Vercel documents Flask as a supported Python deployment and detects an exported Flask `app`; its guide says no custom build/output configuration is needed for the basic Flask setup. Python runtime support is currently marked Beta, so check the deployment logs if the platform behavior changes. [Vercel: Flask on Vercel](https://vercel.com/docs/frameworks/backend/flask), [Vercel: Python Runtime](https://vercel.com/docs/functions/runtimes/python)

The stylesheet is in `public/style.css`, because Vercel serves `public/` files as static assets. Locally, Flask serves that same file through the `/style.css` route.

## Part G — Check the live deployment

Use a document you are allowed to upload. Check all of these manually:

1. The homepage loads with its styling.
2. Upload a DOCX containing a short paragraph and a simple table.
3. Ask a question using exact words from the paragraph and check the displayed source.
4. Ask a question about a table value and check the table row citation.
5. Ask something not in the document and confirm the system does not invent an answer.
6. Select **Clear document**, reload the page, and confirm the current session no longer shows the document.
7. Open the site in another browser/private window and confirm that it has a separate session.

If the deployment fails, open the Vercel project → **Deployments** → the failed deployment → **Build Logs** or **Runtime Logs**. Common causes are a missing `DATABASE_URL`, missing `DOCUMENT_QA_SECRET`, a typo in the environment variable name, or a database connection string copied incorrectly. Do not paste secret values into logs, issue reports, or chat.

## Part H — Make later changes

Edit files locally, then publish each update with:

```powershell
git add .
git status --short
git commit -m "Describe the change"
git push
```

Pushing to `main` triggers a new production deployment when the GitHub repository is connected to Vercel. A push to another branch can create a preview deployment. Review the preview URL before merging changes into `main`. [Vercel: Deploying Git repositories](https://vercel.com/docs/deployments)

## What is not included

This project does not include user accounts, shared document libraries, virus scanning, or OCR for image-only files. Uploaded original files are not retained by the app, but extracted text is stored in the configured PostgreSQL database until cleared. The site is a student project; do not treat it as a secure document portal.
