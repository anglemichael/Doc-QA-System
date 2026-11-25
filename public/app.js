"use strict";

const fileInput = document.getElementById("document");
const sampleButton = document.getElementById("sample-button");
const fileStatus = document.getElementById("file-status");
const questionForm = document.getElementById("question-form");
const askButton = document.getElementById("ask-button");
const answerSection = document.getElementById("answer");
const answerHeading = document.getElementById("answer-heading");
const answerSummary = document.getElementById("answer-summary");
const resultsContainer = document.getElementById("results");

let selectedDocument = null;

function setSelectedDocument(file) {
  if (file && file.size > 4 * 1024 * 1024) {
    selectedDocument = null;
    fileStatus.textContent = "That file exceeds the 4 MiB limit. Choose a smaller document.";
    answerSection.hidden = true;
    return;
  }
  selectedDocument = file;
  fileStatus.textContent = file
    ? `Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KiB)`
    : "No document selected.";
  answerSection.hidden = true;
}

function showError(message) {
  answerSection.hidden = false;
  answerHeading.textContent = "Could not answer";
  answerSummary.textContent = message;
  resultsContainer.replaceChildren();
}

function addEvidenceCard(result, index) {
  const article = document.createElement("article");
  article.className = `evidence${index === 0 ? " best-evidence" : ""}`;

  const heading = document.createElement("div");
  heading.className = "evidence-title";
  const title = document.createElement("h3");
  title.textContent = index === 0 ? "Best matching passage" : "Other matching passage";
  const kind = document.createElement("span");
  kind.textContent = result.kind;
  heading.append(title, kind);

  const quote = document.createElement("blockquote");
  quote.textContent = result.text;
  const source = document.createElement("p");
  source.className = "source";
  source.textContent = `Source: ${result.source}`;
  article.append(heading, quote, source);
  resultsContainer.append(article);
}

fileInput.addEventListener("change", () => {
  const file = fileInput.files && fileInput.files[0];
  setSelectedDocument(file || null);
});

sampleButton.addEventListener("click", async () => {
  sampleButton.disabled = true;
  fileStatus.textContent = "Loading the sample document…";
  try {
    const response = await fetch("/sample.txt", { cache: "no-store" });
    if (!response.ok) throw new Error("The sample document could not be loaded.");
    const text = await response.text();
    setSelectedDocument(new File([text], "sample_document.txt", { type: "text/plain" }));
  } catch (error) {
    fileStatus.textContent = error.message;
  } finally {
    sampleButton.disabled = false;
  }
});

questionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedDocument) {
    showError("Choose a document or load the sample TXT file first.");
    return;
  }

  const question = document.getElementById("question").value.trim();
  if (!question) {
    showError("Enter a question first.");
    return;
  }

  askButton.disabled = true;
  askButton.textContent = "Searching…";
  answerSection.hidden = false;
  answerHeading.textContent = "Searching the document";
  answerSummary.textContent = "The selected document is sent with this question and processed for this request.";
  resultsContainer.replaceChildren();

  try {
    const formData = new FormData();
    formData.append("document", selectedDocument, selectedDocument.name);
    formData.append("question", question);
    const response = await fetch("/ask", { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "The request could not be processed.");

    answerHeading.textContent = data.answer_found ? "Matching evidence" : "No answer found";
    answerSummary.textContent = data.answer_found
      ? `Searched ${data.passage_count} passages in ${data.filename}. The system returns source passages instead of inventing an answer.`
      : (data.message || `No sufficiently matching passage was found in ${data.filename}. Try terms used in the document.`);
    data.results.forEach(addEvidenceCard);
  } catch (error) {
    showError(error.message || "The request failed. Please try again.");
  } finally {
    askButton.disabled = false;
    askButton.textContent = "Find evidence";
  }
});
