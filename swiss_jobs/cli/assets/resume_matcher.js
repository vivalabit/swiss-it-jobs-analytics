(() => {
  const shared = window.LocalSearchApp;
  if (!shared) {
    throw new Error("LocalSearchApp shared helpers are not available.");
  }

  const { esc, addLog, renderErrors } = shared;

    const resumeMatchFormEl = document.querySelector("#resume-match-form");
    const vacancySourceModeEl = document.querySelector("#vacancy_source_mode");
    const vacancySourceModeButtons = Array.from(document.querySelectorAll("[data-vacancy-source-mode]"));
    const vacancySourcePanes = Array.from(document.querySelectorAll("[data-vacancy-source-pane]"));
    const vacancyUrlEl = document.querySelector("#vacancy_url");
    const vacancyIdEl = document.querySelector("#vacancy_id");
    const vacancyDatabaseEl = document.querySelector("#vacancy_database");
    const targetTitleEl = document.querySelector("#target_title");
    const vacancyDescriptionEl = document.querySelector("#job_description");
    const vacancyDescriptionLabelEl = document.querySelector('label[for="job_description"]');
    const resumeLocalQueryEl = document.querySelector("#resume_local_query");
    const resumeLocalSearchEl = document.querySelector("#resume-local-search");
    const resumeLocalResultsEl = document.querySelector("#resume-local-results");
    const resumeResetEl = document.querySelector("#resume-reset");
    const resumePdfInputEl = document.querySelector("#resume_pdf");
    const resumeTextEl = document.querySelector("#resume_text");
    const resumeInputModeEl = document.querySelector("#resume_input_mode");
    const resumeInputModeButtons = Array.from(document.querySelectorAll("[data-resume-input-mode]"));
    const resumeInputPanes = Array.from(document.querySelectorAll("[data-resume-input-pane]"));
    const resumeClearFileEl = document.querySelector("#resume-clear-file");
    const resumeFileNameEl = document.querySelector("#resume-file-name");
    const resumeDropHintEl = document.querySelector("#resume-drop-hint");
    const resumeReviewFileEl = document.querySelector("#resume-review-file");
    const resumeReviewTextEl = document.querySelector("#resume-review-text");
    const resumeReviewPreviewEl = document.querySelector("#resume-review-preview");
    const resumeGenerateCvEl = document.querySelector("#resume-generate-cv");
    const resumeDownloadPdfEl = document.querySelector("#resume-download-pdf");
    const resumeDownloadDocxEl = document.querySelector("#resume-download-docx");
    const resumeStatusEl = document.querySelector("#resume-match-status");
    const resumeVacancyLoadStatusEl = document.querySelector("#resume-vacancy-load-status");
    const resumeVacancyPreviewEl = document.querySelector("#resume-vacancy-preview");
    const resumeScoreCardEl = document.querySelector("#resume-score-card");
    const resumeScoreValueEl = document.querySelector("#resume-score-value");
    const resumeVacancyTitleEl = document.querySelector("#resume-vacancy-title");
    const resumeVacancyMetaEl = document.querySelector("#resume-vacancy-meta");
    const resumeSkillsScoreEl = document.querySelector("#resume-skills-score");
    const resumeExperienceScoreEl = document.querySelector("#resume-experience-score");
    const resumeKeywordsScoreEl = document.querySelector("#resume-keywords-score");
    const resumeSkillsMeterEl = document.querySelector("#resume-skills-meter");
    const resumeExperienceMeterEl = document.querySelector("#resume-experience-meter");
    const resumeKeywordsMeterEl = document.querySelector("#resume-keywords-meter");
    const resumeMatchedKeywordsEl = document.querySelector("#resume-matched-keywords");
    const resumeMissingKeywordsEl = document.querySelector("#resume-missing-keywords");
    const resumeAtsProbabilityEl = document.querySelector("#resume-ats-probability");
    const resumeAtsRingEl = document.querySelector("#resume-ats-ring");
    const resumeAtsMeterEl = document.querySelector("#resume-ats-meter");
    const resumeAtsChecksEl = document.querySelector("#resume-ats-checks");
    const resumeGapBlockersEl = document.querySelector("#resume-gap-blockers");
    const resumeGapStrengthsEl = document.querySelector("#resume-gap-strengths");
    const resumeRecommendationsEl = document.querySelector("#resume-recommendations");
    const resumeResultEl = document.querySelector("#resume_result");
    const resumeMaxFileBytes = 12 * 1024 * 1024;
    const resumeFileReadTimeoutMs = 15000;
    const resumeDocxMimeType = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    const resumeMatchTimeoutMs = 120000;
    const resumeCvGenerateTimeoutMs = 30000;
    let resumePdfObjectUrl = "";
    let resumeDocxObjectUrl = "";
    let resumeLocalSearchResults = [];
    let resumePdfTitle = "Target role";

    function renderKeywordCloud(container, keywords, emptyText) {
      if (!keywords || !keywords.length) {
        container.innerHTML = `<span class="tag">${esc(emptyText)}</span>`;
        return;
      }
      container.innerHTML = keywords.map((keyword) => `<span class="tag keyword">${esc(keyword)}</span>`).join("");
    }

    function renderGapList(container, items, emptyText, icon) {
      if (!container) return;
      if (!items || !items.length) {
        container.innerHTML = `<div class="empty">${esc(emptyText)}</div>`;
        return;
      }
      container.innerHTML = items.map((item) => `
        <div class="resume-gap-item">
          <span class="resume-gap-icon" aria-hidden="true">${esc(icon)}</span>
          <span>${esc(item)}</span>
        </div>
      `).join("");
    }

    function renderAtsCompatibility(ats, emptyText = "Run the matcher to see ATS compatibility.") {
      if (!resumeAtsProbabilityEl || !resumeAtsRingEl || !resumeAtsMeterEl || !resumeAtsChecksEl) return;
      const probability = Math.max(0, Math.min(100, Number(ats?.pass_probability || 0)));
      resumeAtsProbabilityEl.textContent = `${probability}%`;
      resumeAtsRingEl.textContent = `${probability}%`;
      resumeAtsRingEl.style.setProperty("--ats-score", probability);
      resumeAtsMeterEl.style.width = `${probability}%`;
      if (!ats) {
        resumeAtsChecksEl.innerHTML = `<div class="empty">${esc(emptyText)}</div>`;
        return;
      }
      const checks = ats?.checks || {};
      const rows = [
        ["keywords", "Keywords"],
        ["structure", "Structure"],
        ["readability", "Readability"],
        ["format", "Format"],
      ].map(([key, label]) => {
        const item = checks[key] || {};
        const score = Math.max(0, Math.min(100, Number(item.score || 0)));
        const status = ["pass", "warning", "fail"].includes(item.status) ? item.status : "warning";
        const finding = item.finding || "No ATS finding generated yet.";
        return `
          <div class="resume-ats-check is-${status}">
            <span class="resume-ats-check-label">${esc(label)}</span>
            <span class="resume-ats-check-score">${score}%</span>
            <span class="resume-ats-check-finding">${esc(finding)}</span>
          </div>
        `;
      });
      resumeAtsChecksEl.innerHTML = rows.join("");
    }

    function resumeMatchLabel(score) {
      if (score >= 80) return "Very Good Match";
      if (score >= 60) return "Good Match";
      if (score >= 40) return "Partial Match";
      return "Needs Tailoring";
    }

    function setResumeScoreBreakdown(score, breakdown = {}) {
      const normalized = Math.max(0, Math.min(100, Number(score || 0)));
      const skills = Math.max(0, Math.min(100, Number(breakdown.skills ?? normalized)));
      const experience = Math.max(0, Math.min(100, Number(breakdown.experience ?? normalized)));
      const keywords = Math.max(0, Math.min(100, Number(breakdown.keywords ?? normalized)));
      resumeSkillsScoreEl.textContent = `${skills}%`;
      resumeExperienceScoreEl.textContent = `${experience}%`;
      resumeKeywordsScoreEl.textContent = `${keywords}%`;
      resumeSkillsMeterEl.style.width = `${skills}%`;
      resumeExperienceMeterEl.style.width = `${experience}%`;
      resumeKeywordsMeterEl.style.width = `${keywords}%`;
    }

    function vacancyPaneMatches(pane, mode) {
      return String(pane.dataset.vacancySourcePane || "").split(/\\s+/).includes(mode);
    }

    function setVacancySourceMode(mode) {
      const nextMode = ["url", "local", "paste"].includes(mode) ? mode : "url";
      vacancySourceModeEl.value = nextMode;
      vacancySourceModeButtons.forEach((button) => {
        const isActive = button.dataset.vacancySourceMode === nextMode;
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
      });
      vacancySourcePanes.forEach((pane) => {
        pane.hidden = !vacancyPaneMatches(pane, nextMode);
      });
      vacancyDescriptionLabelEl.textContent = nextMode === "paste"
        ? "Paste vacancy text"
        : "Vacancy description fallback";
      if (nextMode === "url") {
        vacancyIdEl.value = "";
        vacancyDatabaseEl.value = "";
        resumeVacancyLoadStatusEl.textContent = "Waiting for vacancy";
        resumeVacancyLoadStatusEl.classList.add("is-muted");
      }
      if (nextMode === "paste") {
        vacancyUrlEl.value = "";
        vacancyIdEl.value = "";
        vacancyDatabaseEl.value = "";
        resumeVacancyLoadStatusEl.textContent = "Using pasted vacancy text";
        resumeVacancyLoadStatusEl.classList.add("is-muted");
        vacancyDescriptionEl.focus();
      }
    }

    function renderResumeLocalResults(payload) {
      const results = payload.results || [];
      resumeLocalSearchResults = results;
      renderErrors(payload.database_errors);
      if (!results.length) {
        resumeLocalResultsEl.innerHTML = '<div class="empty">No local vacancies found.</div>';
        return;
      }
      resumeLocalResultsEl.innerHTML = results.map((job, index) => `
        <button class="resume-local-option" type="button" data-local-vacancy-index="${index}">
          <strong>${esc(job.title || "Untitled vacancy")}</strong>
          <span>${esc([job.company, job.location, job.source].filter(Boolean).join(" · ") || "Local vacancy")}</span>
          ${job.description_preview ? `<span>${esc(job.description_preview.slice(0, 160))}${job.description_preview.length > 160 ? "..." : ""}</span>` : ""}
        </button>
      `).join("");
    }

    async function runResumeLocalSearch() {
      const params = new URLSearchParams({
        q: resumeLocalQueryEl.value.trim(),
        page: "1",
        per_page: "6",
      });
      resumeLocalResultsEl.innerHTML = '<div class="empty">Searching local vacancies...</div>';
      addLog("Resume matcher", "Searching local vacancies.");
      try {
        const response = await fetch(`/api/search?${params.toString()}`);
        const payload = await response.json();
        if (!response.ok) {
          resumeLocalResultsEl.innerHTML = `<div class="error">${esc(payload.error || "Local vacancy search failed.")}</div>`;
          addLog("Resume matcher", payload.error || "Local vacancy search failed.", "error");
          return;
        }
        renderResumeLocalResults(payload);
        addLog("Resume matcher", `Found ${payload.total ?? payload.count ?? 0} local vacancies.`, payload.database_errors?.length ? "warning" : "success");
      } catch (error) {
        const message = error.message || String(error);
        resumeLocalResultsEl.innerHTML = `<div class="error">${esc(message)}</div>`;
        addLog("Resume matcher", message, "error");
      }
    }

    function selectResumeLocalVacancy(index) {
      const job = resumeLocalSearchResults[index];
      if (!job) return;
      vacancyIdEl.value = job.id || "";
      vacancyDatabaseEl.value = job.database || "";
      vacancyUrlEl.value = job.url || "";
      if (!targetTitleEl.value.trim() && job.title) {
        targetTitleEl.value = job.title;
      }
      vacancyDescriptionEl.value = job.description_text || job.description_preview || "";
      resumeLocalResultsEl.querySelectorAll(".resume-local-option").forEach((button) => {
        button.classList.toggle("is-selected", button.dataset.localVacancyIndex === String(index));
      });
      resumeVacancyLoadStatusEl.textContent = "Local vacancy selected";
      resumeVacancyLoadStatusEl.classList.remove("is-muted");
      renderResumeVacancyPreview(job, { target_title: targetTitleEl.value, job_description: vacancyDescriptionEl.value }, job.skills || []);
      addLog("Resume matcher", `Selected local vacancy: ${job.title || job.id || "untitled"}.`, "success");
    }

    function resetResumePreview() {
      resumeVacancyLoadStatusEl.textContent = "Waiting for vacancy";
      resumeVacancyLoadStatusEl.classList.add("is-muted");
      resumeVacancyPreviewEl.innerHTML = `
        <h3>No vacancy loaded yet</h3>
        <div class="resume-preview-tags">
          <span class="tag">Waiting</span>
        </div>
        <p>Paste a vacancy URL or fallback description, then run the matcher to preview the vacancy context used for the analysis.</p>
      `;
      setResumeScoreBreakdown(0);
      resumeScoreValueEl.style.setProperty("--score", 0);
    }

    function renderResumeVacancyPreview(vacancy, payload, requiredKeywords = []) {
      const fallbackText = String(payload.job_description || "").trim();
      const title = vacancy.title || payload.target_title || "Vacancy preview";
      const description = String(vacancy.description_text || fallbackText || "").trim();
      const preview = description
        ? `${description.slice(0, 700)}${description.length > 700 ? "..." : ""}`
        : "The matcher used the URL and available metadata, but no long description was available.";
      const tags = [
        vacancy.location,
        vacancy.company,
        vacancy.source,
        ...requiredKeywords.slice(0, 4),
      ].filter(Boolean);
      resumeVacancyPreviewEl.innerHTML = `
        <h3>${esc(title)}</h3>
        <div class="resume-preview-tags">
          ${tags.length ? tags.map((item) => `<span class="tag">${esc(item)}</span>`).join("") : '<span class="tag">Vacancy context</span>'}
        </div>
        <p>${esc(preview)}</p>
      `;
    }

    function renderResumeRecommendations(items) {
      if (!items || !items.length) {
        resumeRecommendationsEl.innerHTML = '<div class="empty">No recommendations generated.</div>';
        return;
      }
      resumeRecommendationsEl.innerHTML = items.map((item, index) => `
        <div class="resume-recommendation">
          <span class="resume-recommendation-icon">${index + 1}</span>
          <span><strong>${esc(item.split(":")[0] || "Recommendation")}</strong><span>${esc(item.includes(":") ? item.split(":").slice(1).join(":").trim() : item)}</span></span>
        </div>
      `).join("");
    }

    function filePayloadToObjectUrl(file) {
      const binary = atob(file.base64);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
      }
      const blob = new Blob([bytes], { type: file.mime_type || "application/octet-stream" });
      return URL.createObjectURL(blob);
    }

    function clearResumeCvDownloads() {
      if (resumePdfObjectUrl) {
        URL.revokeObjectURL(resumePdfObjectUrl);
        resumePdfObjectUrl = "";
      }
      if (resumeDocxObjectUrl) {
        URL.revokeObjectURL(resumeDocxObjectUrl);
        resumeDocxObjectUrl = "";
      }
      resumeDownloadPdfEl.hidden = true;
      resumeDownloadPdfEl.removeAttribute("href");
      resumeDownloadDocxEl.hidden = true;
      resumeDownloadDocxEl.removeAttribute("href");
    }

    function setResumeCvDownloads(files) {
      clearResumeCvDownloads();
      const pdf = files?.pdf;
      const docx = files?.docx;
      if (pdf?.base64) {
        resumePdfObjectUrl = filePayloadToObjectUrl(pdf);
        resumeDownloadPdfEl.href = resumePdfObjectUrl;
        resumeDownloadPdfEl.download = pdf.filename || "tailored-resume.pdf";
        resumeDownloadPdfEl.hidden = false;
      }
      if (docx?.base64) {
        resumeDocxObjectUrl = filePayloadToObjectUrl(docx);
        resumeDownloadDocxEl.href = resumeDocxObjectUrl;
        resumeDownloadDocxEl.download = docx.filename || "tailored-resume.docx";
        resumeDownloadDocxEl.hidden = false;
      }
    }

    function setResumeGenerateCvState(enabled, label = "Generate CV", hint = "Creates PDF and DOCX files") {
      if (!resumeGenerateCvEl) return;
      resumeGenerateCvEl.disabled = !enabled;
      const textEl = resumeGenerateCvEl.querySelector("span:last-child");
      if (textEl) {
        textEl.innerHTML = `${esc(label)}<small>${esc(hint)}</small>`;
      }
    }

    function readFileAsBase64(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        const timeout = window.setTimeout(() => {
          reader.abort();
          reject(new Error("Resume file reading timed out. Try a smaller PDF/DOCX or paste resume text."));
        }, resumeFileReadTimeoutMs);
        const cleanup = () => window.clearTimeout(timeout);
        reader.addEventListener("load", () => {
          cleanup();
          const value = String(reader.result || "");
          resolve(value.includes(",") ? value.split(",", 2)[1] : value);
        });
        reader.addEventListener("error", () => {
          cleanup();
          reject(reader.error || new Error("Could not read resume file."));
        });
        reader.addEventListener("abort", () => {
          cleanup();
          reject(new Error("Resume file reading was cancelled."));
        });
        reader.readAsDataURL(file);
      });
    }

    function isResumeUploadFile(file) {
      if (!file) return false;
      const name = String(file.name || "").toLowerCase();
      const type = String(file.type || "").toLowerCase();
      return type === "application/pdf"
        || type === resumeDocxMimeType
        || name.endsWith(".pdf")
        || name.endsWith(".docx");
    }

    async function runResumeMatch() {
      const formData = new FormData(resumeMatchFormEl);
      const payload = Object.fromEntries(formData.entries());
      const vacancySourceMode = vacancySourceModeEl.value;
      delete payload.resume_pdf;
      if (vacancySourceMode === "url") {
        delete payload.vacancy_id;
        delete payload.vacancy_database;
        delete payload.target_title;
        delete payload.job_description;
      } else if (vacancySourceMode === "local") {
        if (!payload.vacancy_id) {
          const message = "Select a local vacancy first.";
          resumeStatusEl.textContent = message;
          resumeVacancyLoadStatusEl.textContent = "No local vacancy selected";
          resumeVacancyLoadStatusEl.classList.add("is-muted");
          resumeRecommendationsEl.innerHTML = `<div class="error">${esc(message)}</div>`;
          addLog("Resume matcher", message, "warning");
          return;
        }
      } else if (vacancySourceMode === "paste") {
        delete payload.vacancy_url;
        delete payload.vacancy_id;
        delete payload.vacancy_database;
      }
      resumeStatusEl.textContent = "Generating resume match...";
      resumeVacancyLoadStatusEl.textContent = "Loading vacancy...";
      resumeVacancyLoadStatusEl.classList.add("is-muted");
      resumeScoreCardEl.hidden = true;
      resumeRecommendationsEl.innerHTML = '<div class="empty">Generating resume match...</div>';
      renderKeywordCloud(resumeMatchedKeywordsEl, [], "Waiting");
      renderKeywordCloud(resumeMissingKeywordsEl, [], "Waiting");
      renderAtsCompatibility(null, "Generating ATS compatibility...");
      renderGapList(resumeGapBlockersEl, [], "Generating blockers...", "✕");
      renderGapList(resumeGapStrengthsEl, [], "Generating strengths...", "✓");
      resumeResultEl.value = "";
      resumePdfTitle = "Target role";
      setResumeGenerateCvState(false, "Generate CV", "After analysis completes");
      clearResumeCvDownloads();
      addLog("Resume matcher", "Generating resume match.");

      try {
        const file = resumePdfInputEl.files?.[0];
        if (file && resumeInputModeEl.value !== "paste") {
          if (!isResumeUploadFile(file)) {
            throw new Error("Attach a PDF or DOCX resume file.");
          }
          if (file.size > resumeMaxFileBytes) {
            throw new Error("Resume file is larger than 12MB. Upload a smaller PDF/DOCX or paste resume text.");
          }
          payload.resume_file_name = file.name;
          payload.resume_file_type = file.type || (file.name.toLowerCase().endsWith(".docx") ? resumeDocxMimeType : "application/pdf");
          payload.resume_file_base64 = await readFileAsBase64(file);
        }
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), resumeMatchTimeoutMs);
        let response;
        try {
          response = await fetch("/api/resume-match", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
            signal: controller.signal,
          });
        } catch (error) {
          if (error.name === "AbortError") {
            throw new Error("Resume match timed out. Try a shorter vacancy text or paste resume text instead of uploading a file.");
          }
          throw error;
        } finally {
          window.clearTimeout(timeout);
        }
        const data = await response.json();
        if (!response.ok) {
          const message = data.error || "Resume match failed.";
          resumeStatusEl.textContent = message;
          resumeVacancyLoadStatusEl.textContent = resumeFailureStatus(message);
          resumeVacancyLoadStatusEl.classList.add("is-muted");
          resumeRecommendationsEl.innerHTML = `<div class="error">${esc(message)}</div>`;
          addLog("Resume matcher", message, "error");
          return;
        }
        const vacancy = data.vacancy || {};
        resumeStatusEl.textContent = data.vacancy_found
          ? "Vacancy loaded from local database."
          : data.vacancy_fetched
            ? "Vacancy page fetched from URL."
            : "Using pasted vacancy description because the URL was not found locally or could not be fetched.";
        resumeVacancyLoadStatusEl.textContent = data.vacancy_found || data.vacancy_fetched
          ? "Vacancy loaded successfully"
          : "Using pasted vacancy text";
        resumeVacancyLoadStatusEl.classList.toggle("is-muted", !(data.vacancy_found || data.vacancy_fetched));
        if (data.vacancy_fetch_error) {
          addLog("Resume matcher", data.vacancy_fetch_error, "warning");
        }
        renderResumeVacancyPreview(vacancy, payload, data.required_keywords || []);
        resumeScoreCardEl.hidden = false;
        const score = Number(data.score || 0);
        resumeScoreValueEl.textContent = `${score}%`;
        resumeScoreValueEl.style.setProperty("--score", score);
        setResumeScoreBreakdown(score, data.score_breakdown || {});
        resumeVacancyTitleEl.textContent = resumeMatchLabel(score);
        resumeVacancyMetaEl.textContent = [
          vacancy.company,
          vacancy.location,
          vacancy.source,
        ].filter(Boolean).join(" · ") || (vacancy.title || payload.target_title || "Local keyword alignment");
        renderKeywordCloud(resumeMatchedKeywordsEl, data.matched_keywords || [], "No matched keywords yet");
        renderKeywordCloud(resumeMissingKeywordsEl, data.missing_keywords || [], "No missing keywords found");
        renderAtsCompatibility(data.ats_compatibility || null);
        renderGapList(
          resumeGapBlockersEl,
          data.gap_analysis?.blockers || [],
          "No screening blockers found.",
          "✕",
        );
        renderGapList(
          resumeGapStrengthsEl,
          data.gap_analysis?.strengths || data.key_strengths || [],
          "No strong points detected yet.",
          "✓",
        );
        renderResumeRecommendations(data.recommendations || []);
        resumeResultEl.value = data.tailored_resume || "";
        resumePdfTitle = data.tailored_resume_pdf_title || vacancy.title || payload.target_title || "Target role";
        setResumeGenerateCvState(Boolean(resumeResultEl.value.trim()));
        clearResumeCvDownloads();
        renderErrors(data.database_errors);
        addLog(
          "Resume matcher",
          `Generated resume match with ${Number(data.score || 0)}% keyword alignment${data.resume_file_text_extracted || data.resume_pdf_text_extracted ? " from attached file" : ""}.`,
          data.vacancy_found ? "success" : "warning",
        );
      } catch (error) {
        const message = error.message || String(error);
        resumeStatusEl.textContent = message;
        resumeVacancyLoadStatusEl.textContent = resumeFailureStatus(message);
        resumeVacancyLoadStatusEl.classList.add("is-muted");
        resumeRecommendationsEl.innerHTML = `<div class="error">${esc(message)}</div>`;
        addLog("Resume matcher", message, "error");
      }
    }

    async function generateResumeCv() {
      const tailoredResume = resumeResultEl.value.trim();
      if (!tailoredResume) {
        addLog("Resume matcher", "No generated resume text for CV files.", "warning");
        return;
      }
      setResumeGenerateCvState(false, "Generating CV", "Preparing downloads");
      clearResumeCvDownloads();
      addLog("Resume matcher", "Generating tailored resume PDF and DOCX.");
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), resumeCvGenerateTimeoutMs);
      try {
        const response = await fetch("/api/resume-cv", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target_title: resumePdfTitle,
            tailored_resume: tailoredResume,
          }),
          signal: controller.signal,
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || "CV generation failed.");
        }
        setResumeCvDownloads(data);
        addLog("Resume matcher", "Generated tailored resume PDF and DOCX.", "success");
      } catch (error) {
        const message = error.name === "AbortError"
          ? "CV generation timed out. Try shortening the resume text."
          : error.message || String(error);
        addLog("Resume matcher", message, "error");
      } finally {
        window.clearTimeout(timeout);
        setResumeGenerateCvState(true);
      }
    }

    function syncResumeFileState() {
      const file = resumePdfInputEl.files?.[0];
      const hasFile = Boolean(file);
      resumeFileNameEl.textContent = file ? file.name : "No PDF or DOCX selected";
      resumeClearFileEl.hidden = !hasFile;
      resumeDropHintEl.hidden = hasFile;
      syncResumeReviewState();
    }

    function syncResumeReviewState() {
      const file = resumePdfInputEl.files?.[0];
      const text = resumeTextEl.value.trim();
      resumeReviewFileEl.textContent = file ? file.name : "No PDF or DOCX selected";
      resumeReviewTextEl.textContent = text
        ? `${text.length.toLocaleString()} characters pasted`
        : "No pasted resume text";
      resumeReviewPreviewEl.textContent = text
        ? text.slice(0, 360)
        : file
          ? "Resume file is attached and ready for analysis."
          : "Nothing to review yet.";
    }

    function setResumeInputMode(mode) {
      const nextMode = ["upload", "paste", "review"].includes(mode) ? mode : "upload";
      resumeInputModeEl.value = nextMode;
      resumeInputModeButtons.forEach((button) => {
        const isActive = button.dataset.resumeInputMode === nextMode;
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
      });
      resumeInputPanes.forEach((pane) => {
        pane.hidden = pane.dataset.resumeInputPane !== nextMode;
      });
      syncResumeReviewState();
      if (nextMode === "paste") {
        resumeTextEl.focus();
      }
    }

    function resumeFailureStatus(message) {
      const lower = String(message || "").toLowerCase();
      if (lower.includes("pdf") || lower.includes("docx") || lower.includes("resume")) {
        return "Resume file failed";
      }
      if (lower.includes("vacancy") || lower.includes("url") || lower.includes("fetch")) {
        return "Vacancy load failed";
      }
      return "Resume match failed";
    }

    resumeMatchFormEl.addEventListener("submit", (event) => {
      event.preventDefault();
      runResumeMatch();
    });
    resumeResetEl.addEventListener("click", () => {
      resumeMatchFormEl.reset();
      setVacancySourceMode("url");
      setResumeInputMode("upload");
      resumeLocalSearchResults = [];
      resumeLocalResultsEl.innerHTML = '<div class="empty">Search local vacancies to select one.</div>';
      resumeStatusEl.textContent = "No resume match generated yet.";
      resumeScoreCardEl.hidden = true;
      renderKeywordCloud(resumeMatchedKeywordsEl, [], "Waiting");
      renderKeywordCloud(resumeMissingKeywordsEl, [], "Waiting");
      renderAtsCompatibility(null);
      resumeRecommendationsEl.innerHTML = '<div class="empty">Run the matcher to see recommendations.</div>';
      resumeResultEl.value = "";
      resumePdfTitle = "Target role";
      setResumeGenerateCvState(false);
      syncResumeFileState();
      resetResumePreview();
      clearResumeCvDownloads();
      addLog("Resume matcher", "Cleared resume matcher inputs.");
    });
    resumeGenerateCvEl?.addEventListener("click", generateResumeCv);
    vacancySourceModeButtons.forEach((button) => {
      button.addEventListener("click", () => {
        setVacancySourceMode(button.dataset.vacancySourceMode || "url");
      });
    });
    resumeLocalSearchEl.addEventListener("click", runResumeLocalSearch);
    resumeLocalQueryEl.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      runResumeLocalSearch();
    });
    resumeLocalResultsEl.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-local-vacancy-index]");
      if (!button) return;
      selectResumeLocalVacancy(Number(button.dataset.localVacancyIndex));
    });
    resumeInputModeButtons.forEach((button) => {
      button.addEventListener("click", () => {
        setResumeInputMode(button.dataset.resumeInputMode || "upload");
      });
    });
    resumeTextEl.addEventListener("input", syncResumeReviewState);
    resumePdfInputEl.addEventListener("change", syncResumeFileState);
    resumeClearFileEl.addEventListener("click", () => {
      resumePdfInputEl.value = "";
      syncResumeFileState();
      addLog("Resume matcher", "Removed attached resume file.");
    });
    setVacancySourceMode(vacancySourceModeEl.value);
    setResumeInputMode(resumeInputModeEl.value);
    renderKeywordCloud(resumeMatchedKeywordsEl, [], "Waiting");
    renderKeywordCloud(resumeMissingKeywordsEl, [], "Waiting");
})();
