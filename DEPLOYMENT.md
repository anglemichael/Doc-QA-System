# Continue from the existing GitHub commit and deploy on Vercel

The repository is already initialized on the `main` branch and connected to GitHub. **Do not run `git init` again.** This version removes the database: the browser sends its selected file with each question and the Flask function extracts and searches it in memory. No database or Vercel environment variables are required.

## 1. Review and commit this update

Open PowerShell in the project folder:

```powershell
Set-Location "C:\Users\angel\Documents\Codex\2026-11-25\t\outputs\document_qa_website"
git status --short --branch
```

Check the list. It should show the application, browser script, sample TXT, documentation, and dependency changes. It should not show `.venv/`, `instance/`, `.env`, a password, a database URL, or the assignment document. The `.gitignore` file excludes local environments and secret files.

Stage, review, commit, and push to the existing remote:

```powershell
git add -A
git status --short
git commit -m "Make document QA demo stateless"
git push origin main
```

If Git reports there is nothing to commit, check the status and confirm that these updated files are already committed. Do not reinitialize the repository or change the existing `origin` remote.

## 2. Let Vercel deploy from GitHub

If the `Doc-QA-System` repository is already connected to a Vercel project, pushing the `main` commit should start a deployment automatically. Open that project in Vercel and choose **Deployments** to watch the latest build. Vercel creates deployments from pushes to a connected Git repository. [Vercel Git deployments](https://vercel.com/docs/deployments)

If the repository has not been imported to Vercel yet:

1. Sign in to Vercel using the GitHub account that owns the repository.
2. Choose **Add New → Project** and import `Doc-QA-System`.
3. Set the root directory to the repository root.
4. Let Vercel detect the Flask app. The root `app.py` exports a Flask variable named `app`, and dependencies are listed in `requirements.txt`.
5. Leave Build Command and Output Directory at the detected defaults, then deploy.

Vercel documents Flask deployment from an exported `app` in `app.py`. Static assets belong in `public/`; this project puts `style.css`, `app.js`, and the sample document there. [Vercel Flask guide](https://vercel.com/docs/frameworks/backend/flask)

## 3. No database or environment variables

This version does not use SQLite, Neon, Postgres, `DATABASE_URL`, or `DOCUMENT_QA_SECRET`. It rebuilds the knowledge base for each question from the file sent in that request. If you already created a Neon database while following the earlier guide, this app will not connect to it; you can leave it unused.

The browser holds the file only while the page remains open and resends it for each question. The Flask function processes each request and does not save the uploaded file or extracted passages. This keeps the demo simple, but the document is transmitted to the deployed site each time. Use only documents you are allowed to send to that service.

The upload limit is 4 MiB. Vercel's ordinary Function body limit is 4.5 MB, so the app keeps a margin for multipart request overhead. [Vercel Function limits](https://vercel.com/docs/functions/limitations)

## 4. Demonstrate the deployed website

After the deployment is Ready, open its URL and:

1. Click **Use sample TXT document**.
2. Ask `Who coordinates the campus garden project?` The evidence should include **Asha Rao**.
3. Ask `Where is the garden located?` The evidence should include **North Courtyard**.
4. Ask `How much is the project budget?` The evidence should include **2,500 rupees**.
5. Ask `What is the principal's office phone number?` The app should show that no matching evidence was found.
6. Select a DOCX of your own, if you want to demonstrate the primary format. The selected file is sent again with every question; refreshing the page clears the browser's selection.

The sample is `public/sample.txt`; the **Use sample TXT document** button loads it without making the examiner find a separate file.

## 5. Publish later updates

After editing the project, repeat the status check, commit, and push steps above. Each push to `main` can create another Production deployment. Check the latest Vercel deployment logs if the build fails.

## Limitations

This is a stateless classroom demo. It has no accounts, saved chat history, saved knowledge base, OCR, or shared document library. Because the file is reprocessed for every question, use short documents. Vercel rejects requests above its function body limit.
