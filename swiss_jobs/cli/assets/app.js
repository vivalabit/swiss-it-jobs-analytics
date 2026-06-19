    const appEl = document.querySelector("#app");
    const menuButtons = Array.from(document.querySelectorAll("[data-view-target]"));
    const vacanciesWorkspaceEl = document.querySelector("#vacancies-workspace");
    const parserWorkspaceEl = document.querySelector("#parser-workspace");
    const aiAnalyseWorkspaceEl = document.querySelector("#ai-analyse-workspace");
    const resumeMatcherWorkspaceEl = document.querySelector("#resume-matcher-workspace");
    const publicStatsWorkspaceEl = document.querySelector("#public-stats-workspace");
    const settingsWorkspaceEl = document.querySelector("#settings-workspace");
    const openAiSettingsFormEl = document.querySelector("#openai-settings-form");
    const openAiApiKeyEl = document.querySelector("#openai_api_key");
    const logToggleEl = document.querySelector("#log-toggle");
    const logDrawerEl = document.querySelector("#log-drawer");
    const logCloseEl = document.querySelector("#log-close");
    const logListEl = document.querySelector("#log-list");
    const logClearEl = document.querySelector("#log-clear");
    const workspaceKickerEl = document.querySelector("#workspace-kicker");
    const form = document.querySelector("#search-form");
    const resultsEl = document.querySelector("#results");
    const errorsEl = document.querySelector("#errors");
    const databaseSummaryEl = document.querySelector("#database-summary");
    const paginationEl = document.querySelector("#pagination");
    const subtitleEl = document.querySelector("#subtitle");
    const resetBtn = document.querySelector("#reset");
    const resultTitleEl = document.querySelector("#result-title");
    const salaryMinInput = document.querySelector("#salary_min");
    const salaryMaxInput = document.querySelector("#salary_max");
    const salaryMinRange = document.querySelector("#salary_min_range");
    const salaryMaxRange = document.querySelector("#salary_max_range");
    const salaryMinText = document.querySelector("#salary_min_text");
    const salaryMaxText = document.querySelector("#salary_max_text");
    const salaryTrack = document.querySelector("#salary-track");
    const salaryRangeMax = Number(salaryMaxRange.max);
    const pageSize = 10;
    const maxLogEntries = 80;
    const logs = [];
    const parserRunState = {
      runId: "",
      lastSeq: 0,
      timer: 0,
      status: "idle",
    };
    const aiAnalysisRunState = {
      runId: "",
      lastSeq: 0,
      timer: 0,
      status: "idle",
    };
    const publicStatsRunState = {
      runId: "",
      lastSeq: 0,
      timer: 0,
      status: "idle",
    };
    let currentPage = 1;
    let currentView = "vacancies";

    const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[char]));
    const formatChf = (value) => `${Number(value).toLocaleString("en-US")} CHF`;
    const viewLabels = {
      vacancies: "Vacancy Browser",
      search: "Vacancy Search",
      "ai-analyse": "AI Analyse",
      "resume-matcher": "Resume matcher",
      "public-stats": "Public Stats",
      settings: "Settings",
    };

    function formatLogTime(date) {
      return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    }

    function renderLogs() {
      if (!logs.length) {
        logListEl.innerHTML = '<div class="empty">No log entries yet.</div>';
        return;
      }
      logListEl.innerHTML = logs.map((entry) => `
        <article class="log-entry is-${esc(entry.level)}">
          <div class="log-entry-head">
            <span class="log-entry-title">${esc(entry.title)}</span>
            <span class="log-entry-time">${esc(entry.time)}</span>
          </div>
          <p class="log-entry-message">${esc(entry.message)}</p>
        </article>
      `).join("");
      logListEl.scrollTop = 0;
    }

    function addLog(title, message, level = "info") {
      logs.unshift({ title, message, level, time: formatLogTime(new Date()) });
      if (logs.length > maxLogEntries) logs.length = maxLogEntries;
      renderLogs();
    }

    async function saveOpenAiSettings() {
      const payload = {
        api_key: openAiApiKeyEl.value.trim(),
      };
      try {
        const response = await fetch("/api/settings/openai", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || "Failed to save OpenAI settings.");
        }
        openAiApiKeyEl.value = "";
        addLog("Settings", "Saved API token.", "success");
      } catch (error) {
        addLog("Settings", error.message || String(error), "error");
      }
    }

    function setLogDrawer(open) {
      logDrawerEl.classList.toggle("is-open", open);
      logDrawerEl.setAttribute("aria-hidden", String(!open));
      logToggleEl.setAttribute("aria-expanded", String(open));
    }

    function parserLogTitle(entry) {
      const source = entry.source ? ` ${entry.source}` : "";
      const stream = entry.stream && entry.stream !== "system" ? ` ${entry.stream}` : "";
      return `Parser${source}${stream}`;
    }

    function ingestParserLogs(payload) {
      for (const entry of payload.logs || []) {
        parserRunState.lastSeq = Math.max(parserRunState.lastSeq, Number(entry.seq || 0));
        addLog(parserLogTitle(entry), entry.message || "", entry.level || "info");
      }
      parserRunState.status = payload.status || parserRunState.status;
    }

    async function pollParserRun() {
      if (!parserRunState.runId) return;
      try {
        const params = new URLSearchParams({
          run_id: parserRunState.runId,
          after: String(parserRunState.lastSeq),
        });
        const response = await fetch(`/api/parser-runs?${params.toString()}`);
        const payload = await response.json();
        if (!response.ok) {
          addLog("Parser", payload.error || "Failed to read parser logs.", "error");
          window.clearInterval(parserRunState.timer);
          parserRunState.timer = 0;
          return;
        }
        ingestParserLogs(payload);
        if (["completed", "failed"].includes(payload.status)) {
          window.clearInterval(parserRunState.timer);
          parserRunState.timer = 0;
          parserRunState.runId = "";
          loadFacets().then(() => runSearch(1)).catch((error) => {
            addLog("Vacancy Search", error.message || String(error), "error");
          });
        }
      } catch (error) {
        addLog("Parser", error.message || String(error), "error");
        window.clearInterval(parserRunState.timer);
        parserRunState.timer = 0;
      }
    }

    function collectParserPayload() {
      const sources = Array.from(document.querySelectorAll('input[name="parser_source"]:checked'))
        .map((input) => input.value);
      return {
        sources,
        mode: document.querySelector("#parser_mode")?.value || "new",
        canton: document.querySelector("#parser_canton")?.value || "",
        term: document.querySelector("#parser_term")?.value || "",
        location: document.querySelector("#parser_location")?.value || "",
        max_pages: document.querySelector("#parser_pages")?.value || "",
        detail_limit: document.querySelector("#parser_detail_limit")?.value || "",
      };
    }

    async function startParserRun() {
      if (parserRunState.timer) {
        addLog("Vacancy Collection", "Parser run is already active.", "warning");
        setLogDrawer(true);
        return;
      }
      const payload = collectParserPayload();
      if (!payload.sources.length) {
        addLog("Vacancy Collection", "Select at least one parser source.", "error");
        setLogDrawer(true);
        return;
      }
      addLog("Vacancy Collection", `Starting parser run for ${payload.sources.join(", ")}.`);
      setLogDrawer(true);
      try {
        const response = await fetch("/api/parser-runs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
          addLog("Vacancy Collection", data.error || "Failed to start parser run.", "error");
          return;
        }
        parserRunState.runId = data.id;
        parserRunState.lastSeq = 0;
        parserRunState.status = data.status;
        ingestParserLogs(data);
        parserRunState.timer = window.setInterval(pollParserRun, 1000);
        pollParserRun();
      } catch (error) {
        addLog("Vacancy Collection", error.message || String(error), "error");
      }
    }

    function aiAnalysisLogTitle(entry) {
      const source = entry.source ? ` ${entry.source}` : "";
      const stream = entry.stream && entry.stream !== "system" ? ` ${entry.stream}` : "";
      return `AI Analyse${source}${stream}`;
    }

    function ingestAiAnalysisLogs(payload) {
      for (const entry of payload.logs || []) {
        aiAnalysisRunState.lastSeq = Math.max(aiAnalysisRunState.lastSeq, Number(entry.seq || 0));
        addLog(aiAnalysisLogTitle(entry), entry.message || "", entry.level || "info");
      }
      aiAnalysisRunState.status = payload.status || aiAnalysisRunState.status;
    }

    async function pollAiAnalysisRun() {
      if (!aiAnalysisRunState.runId) return;
      try {
        const params = new URLSearchParams({
          run_id: aiAnalysisRunState.runId,
          after: String(aiAnalysisRunState.lastSeq),
        });
        const response = await fetch(`/api/ai-analysis-runs?${params.toString()}`);
        const payload = await response.json();
        if (!response.ok) {
          addLog("AI Analyse", payload.error || "Failed to read AI analysis logs.", "error");
          window.clearInterval(aiAnalysisRunState.timer);
          aiAnalysisRunState.timer = 0;
          return;
        }
        ingestAiAnalysisLogs(payload);
        if (["completed", "failed"].includes(payload.status)) {
          window.clearInterval(aiAnalysisRunState.timer);
          aiAnalysisRunState.timer = 0;
          aiAnalysisRunState.runId = "";
          loadFacets().then(() => runSearch(1)).catch((error) => {
            addLog("Vacancy Search", error.message || String(error), "error");
          });
        }
      } catch (error) {
        addLog("AI Analyse", error.message || String(error), "error");
        window.clearInterval(aiAnalysisRunState.timer);
        aiAnalysisRunState.timer = 0;
      }
    }

    function collectAiAnalysisPayload() {
      const sources = Array.from(document.querySelectorAll('input[name="analysis_source"]:checked'))
        .map((input) => input.value);
      return {
        sources,
        scope: document.querySelector("#analysis_scope")?.value || "new vacancies only",
        model: document.querySelector("#analysis_model")?.value || "gpt-5-nano",
        first_seen_from: document.querySelector("#analysis_date_from")?.value || "",
        first_seen_to: document.querySelector("#analysis_date_to")?.value || "",
        limit: document.querySelector("#analysis_limit")?.value || "",
      };
    }

    async function startAiAnalysisRun() {
      if (aiAnalysisRunState.timer) {
        addLog("AI Analyse", "AI analysis run is already active.", "warning");
        setLogDrawer(true);
        return;
      }
      const payload = collectAiAnalysisPayload();
      if (!payload.sources.length) {
        addLog("AI Analyse", "Select at least one AI analysis source.", "error");
        setLogDrawer(true);
        return;
      }
      addLog("AI Analyse", `Starting AI analysis for ${payload.sources.join(", ")} with ${payload.model}.`);
      setLogDrawer(true);
      try {
        const response = await fetch("/api/ai-analysis-runs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
          addLog("AI Analyse", data.error || "Failed to start AI analysis run.", "error");
          return;
        }
        aiAnalysisRunState.runId = data.id;
        aiAnalysisRunState.lastSeq = 0;
        aiAnalysisRunState.status = data.status;
        ingestAiAnalysisLogs(data);
        aiAnalysisRunState.timer = window.setInterval(pollAiAnalysisRun, 1000);
        pollAiAnalysisRun();
      } catch (error) {
        addLog("AI Analyse", error.message || String(error), "error");
      }
    }

    function publicStatsLogTitle(entry) {
      const stage = entry.source ? ` ${entry.source}` : "";
      const stream = entry.stream && entry.stream !== "system" ? ` ${entry.stream}` : "";
      return `Public Stats${stage}${stream}`;
    }

    function ingestPublicStatsLogs(payload) {
      for (const entry of payload.logs || []) {
        publicStatsRunState.lastSeq = Math.max(publicStatsRunState.lastSeq, Number(entry.seq || 0));
        addLog(publicStatsLogTitle(entry), entry.message || "", entry.level || "info");
      }
      publicStatsRunState.status = payload.status || publicStatsRunState.status;
    }

    async function pollPublicStatsRun() {
      if (!publicStatsRunState.runId) return;
      try {
        const params = new URLSearchParams({
          run_id: publicStatsRunState.runId,
          after: String(publicStatsRunState.lastSeq),
        });
        const response = await fetch(`/api/public-stats-runs?${params.toString()}`);
        const payload = await response.json();
        if (!response.ok) {
          addLog("Public Stats", payload.error || "Failed to read public stats logs.", "error");
          window.clearInterval(publicStatsRunState.timer);
          publicStatsRunState.timer = 0;
          return;
        }
        ingestPublicStatsLogs(payload);
        if (["completed", "failed"].includes(payload.status)) {
          window.clearInterval(publicStatsRunState.timer);
          publicStatsRunState.timer = 0;
          publicStatsRunState.runId = "";
        }
      } catch (error) {
        addLog("Public Stats", error.message || String(error), "error");
        window.clearInterval(publicStatsRunState.timer);
        publicStatsRunState.timer = 0;
      }
    }

    function collectPublicStatsPayload() {
      const sources = Array.from(document.querySelectorAll('input[name="stats_source"]:checked'))
        .map((input) => input.value);
      return {
        sources,
        snapshot_date: document.querySelector("#stats_snapshot_date")?.value || "",
        salary_group_minimum: document.querySelector("#stats_min_salary_count")?.value || "",
        output_dir: document.querySelector("#stats_output_dir")?.value || "public_stats",
        site_dir: document.querySelector("#stats_site_dir")?.value || "site/public",
        sync_site: true,
      };
    }

    async function startPublicStatsRun() {
      if (publicStatsRunState.timer) {
        addLog("Public Stats", "Public stats build is already active.", "warning");
        setLogDrawer(true);
        return;
      }
      const payload = collectPublicStatsPayload();
      if (!payload.sources.length) {
        addLog("Public Stats", "Select at least one public stats source.", "error");
        setLogDrawer(true);
        return;
      }
      addLog("Public Stats", `Starting public stats build for ${payload.sources.join(", ")}.`);
      setLogDrawer(true);
      try {
        const response = await fetch("/api/public-stats-runs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
          addLog("Public Stats", data.error || "Failed to start public stats build.", "error");
          return;
        }
        publicStatsRunState.runId = data.id;
        publicStatsRunState.lastSeq = 0;
        publicStatsRunState.status = data.status;
        ingestPublicStatsLogs(data);
        publicStatsRunState.timer = window.setInterval(pollPublicStatsRun, 1000);
        pollPublicStatsRun();
      } catch (error) {
        addLog("Public Stats", error.message || String(error), "error");
      }
    }

    function syncSalaryTrack() {
      const min = Number(salaryMinRange.value);
      const max = Number(salaryMaxRange.value);
      const left = (min / salaryRangeMax) * 100;
      const right = (max / salaryRangeMax) * 100;
      salaryTrack.style.background = `linear-gradient(90deg, #e5e7eb 0%, #e5e7eb ${left}%, var(--accent) ${left}%, var(--accent) ${right}%, #e5e7eb ${right}%, #e5e7eb 100%)`;
      salaryMinText.textContent = min > 0 ? formatChf(min) : "Any min";
      salaryMaxText.textContent = max < salaryRangeMax ? formatChf(max) : "Any max";
    }

    function syncSalaryInputsFromRange(changed) {
      let min = Number(salaryMinRange.value);
      let max = Number(salaryMaxRange.value);
      if (min > max) {
        if (changed === "min") {
          max = min;
          salaryMaxRange.value = String(max);
        } else {
          min = max;
          salaryMinRange.value = String(min);
        }
      }
      salaryMinInput.value = min > 0 ? String(min) : "";
      salaryMaxInput.value = max < salaryRangeMax ? String(max) : "";
      syncSalaryTrack();
    }

    function syncSalaryRangeFromInputs() {
      const min = Math.max(0, Math.min(Number(salaryMinInput.value || 0), salaryRangeMax));
      const maxRaw = salaryMaxInput.value ? Number(salaryMaxInput.value) : salaryRangeMax;
      const max = Math.max(0, Math.min(maxRaw, salaryRangeMax));
      salaryMinRange.value = String(Math.min(min, max));
      salaryMaxRange.value = String(Math.max(min, max));
      syncSalaryTrack();
    }

    function setOptions(select, items) {
      const current = select.value;
      select.innerHTML = '<option value="">Any</option>' + items.map((item) => {
        const label = `${item.value} (${item.count})`;
        return `<option value="${esc(item.value)}">${esc(label)}</option>`;
      }).join("");
      select.value = current;
    }

    function setDatalist(id, items) {
      document.querySelector(id).innerHTML = items.map((item) =>
        `<option value="${esc(item.value)}"></option>`
      ).join("");
    }

    function mergeFacetItems(items) {
      const merged = new Map();
      for (const item of items) {
        const key = item.value;
        if (!key) continue;
        merged.set(key, (merged.get(key) || 0) + Number(item.count || 0));
      }
      return Array.from(merged.entries())
        .map(([value, count]) => ({ value, count }))
        .sort((left, right) => right.count - left.count || left.value.localeCompare(right.value));
    }

    function normalizeDateParam(key, value) {
      if (!["date_from", "date_to"].includes(key)) return value;
      const match = value.match(/^(\\d{2})\\.(\\d{2})\\.(\\d{4})$/);
      if (!match) return value;
      return `${match[3]}-${match[2]}-${match[1]}`;
    }

    function buildParams(page = currentPage) {
      const data = new FormData(form);
      const params = new URLSearchParams();
      for (const [key, value] of data.entries()) {
        const clean = String(value).trim();
        if (clean) params.set(key, normalizeDateParam(key, clean));
      }
      params.set("page", String(page));
      params.set("per_page", String(pageSize));
      return params;
    }

    function activateMenu(view) {
      for (const button of menuButtons) {
        const isActive = button.dataset.viewTarget === view;
        button.classList.toggle("is-active", isActive);
        if (isActive) {
          button.setAttribute("aria-current", "page");
        } else {
          button.removeAttribute("aria-current");
        }
      }
    }

    function setView(view, options = {}) {
      currentView = view;
      appEl.classList.remove("view-vacancies", "view-search", "view-ai-analyse", "view-resume-matcher", "view-public-stats", "view-settings");
      appEl.classList.add(`view-${view}`);
      activateMenu(view);

      const isParser = view === "search";
      const isAiAnalyse = view === "ai-analyse";
      const isResumeMatcher = view === "resume-matcher";
      const isPublicStats = view === "public-stats";
      const isSettings = view === "settings";
      vacanciesWorkspaceEl.hidden = isParser || isAiAnalyse || isResumeMatcher || isPublicStats || isSettings;
      parserWorkspaceEl.hidden = !isParser;
      aiAnalyseWorkspaceEl.hidden = !isAiAnalyse;
      resumeMatcherWorkspaceEl.hidden = !isResumeMatcher;
      publicStatsWorkspaceEl.hidden = !isPublicStats;
      settingsWorkspaceEl.hidden = !isSettings;

      if (view === "vacancies") {
        workspaceKickerEl.textContent = "Vacancy Browser";
        if (options.resetFilters) {
          form.reset();
          syncSalaryInputsFromRange();
          currentPage = 1;
          runSearch(1);
        }
        return;
      }

    }

    function renderErrors(errors) {
      if (!errors || !errors.length) {
        errorsEl.innerHTML = "";
        return;
      }
      errorsEl.innerHTML = `<div class="error">${esc(errors.length)} local database error(s). Check terminal output or database schema.</div>`;
    }

    window.LocalSearchApp = {
      esc,
      addLog,
      renderErrors,
    };

    function renderSummaryBlock(title, items) {
      if (!items || !items.length) return "";
      return `
        <div class="summary-block">
          <p class="summary-title">${esc(title)}</p>
          <div class="summary-list">
            ${items.map((item) => `
              <div class="summary-item">
                <span title="${esc(item.path || item.value || item.label)}">${esc(item.label || item.value)}</span>
                <span class="summary-count">${esc(item.count)}</span>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    }

    function getVisiblePages(page, totalPages) {
      if (totalPages <= 7) {
        return Array.from({ length: totalPages }, (_, index) => index + 1);
      }
      const pages = new Set([1, totalPages, page - 1, page, page + 1]);
      if (page <= 3) {
        pages.add(2);
        pages.add(3);
        pages.add(4);
      }
      if (page >= totalPages - 2) {
        pages.add(totalPages - 3);
        pages.add(totalPages - 2);
        pages.add(totalPages - 1);
      }
      return [...pages]
        .filter((item) => item >= 1 && item <= totalPages)
        .sort((left, right) => left - right);
    }

    function renderPagination(payload) {
      const totalPages = Number(payload.total_pages || 1);
      const page = Number(payload.page || 1);
      if (totalPages <= 1) {
        paginationEl.innerHTML = "";
        return;
      }
      const pages = getVisiblePages(page, totalPages);
      const pageButtons = [];
      let previousPage = 0;
      for (const item of pages) {
        if (previousPage && item - previousPage > 1) {
          pageButtons.push('<span class="page-gap" aria-hidden="true">...</span>');
        }
        pageButtons.push(`
          <button class="page-btn ${item === page ? "is-active" : ""}" type="button" data-page="${item}" ${item === page ? 'aria-current="page"' : ""}>
            ${item}
          </button>
        `);
        previousPage = item;
      }
      paginationEl.innerHTML = `
        <button class="page-btn" type="button" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""} aria-label="Previous page">‹</button>
        ${pageButtons.join("")}
        <button class="page-btn" type="button" data-page="${page + 1}" ${page >= totalPages ? "disabled" : ""} aria-label="Next page">›</button>
      `;
    }

    function isPlainObject(value) {
      return value && typeof value === "object" && !Array.isArray(value);
    }

    function hasDetailValue(value) {
      if (value === null || value === undefined || value === "") return false;
      if (Array.isArray(value)) return value.length > 0;
      if (isPlainObject(value)) return Object.keys(value).length > 0;
      return true;
    }

    function formatDetailValue(value) {
      if (Array.isArray(value)) return value.join(", ");
      if (isPlainObject(value)) return JSON.stringify(value);
      if (typeof value === "boolean") return value ? "Yes" : "No";
      return String(value ?? "");
    }

    function makeDomId(prefix, value, index) {
      const clean = String(value || index).replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
      return `${prefix}-${clean || index}-${index}`;
    }

    function renderDetailGrid(rows) {
      const items = rows.filter(([, value]) => hasDetailValue(value));
      if (!items.length) return "";
      return `
        <div class="details-grid">
          ${items.map(([label, value]) => `
            <div class="detail-item">
              <span class="detail-label">${esc(label)}</span>
              <div class="detail-value">${esc(formatDetailValue(value))}</div>
            </div>
          `).join("")}
        </div>
      `;
    }

    function renderJsonSection(title, value) {
      if (!hasDetailValue(value)) return "";
      return `
        <section class="detail-section json-section" hidden>
          <h3 class="detail-section-title">${esc(title)}</h3>
          <pre class="detail-json">${esc(JSON.stringify(value, null, 2))}</pre>
        </section>
      `;
    }

    function renderJobDetails(job, detailsId) {
      const jsonSections = [
        renderJsonSection("Analytics", job.analytics),
        renderJsonSection("LLM analysis", job.llm_analysis),
        renderJsonSection("Job posting schema", job.job_posting_schema),
        renderJsonSection("Raw vacancy data", job.raw),
      ].filter(Boolean).join("");
      const rows = [
        ["Vacancy ID", job.id],
        ["Database", job.database],
        ["Source", job.source],
        ["URL", job.url],
        ["Company", job.company],
        ["Location", job.location],
        ["Employment type", job.employment_type],
        ["Role", job.role],
        ["Seniority", job.seniority],
        ["Detected seniority", job.detected_seniority],
        ["Remote mode", job.remote_mode],
        ["Salary", job.salary],
        ["Salary minimum", job.salary_min],
        ["Salary maximum", job.salary_max],
        ["Salary currency", job.salary_currency],
        ["Salary unit", job.salary_unit],
        ["Published", job.publication_date],
        ["First seen", job.first_seen_at],
        ["Last seen", job.last_seen_at],
        ["Detail skipped", job.detail_schema_skipped],
        ["Detail error", job.detail_schema_error],
        ["LLM model", job.llm_model],
        ["LLM analyzed at", job.llm_analyzed_at],
      ];
      return `
        <section class="job-details-panel" id="${detailsId}" hidden>
          ${renderDetailGrid(rows)}
          ${job.description_text ? `
            <section class="detail-section">
              <h3 class="detail-section-title">Description</h3>
              <p class="detail-description">${esc(job.description_text)}</p>
            </section>
          ` : ""}
          ${jsonSections ? `
            <button class="details-toggle json-toggle" type="button" aria-expanded="false" data-json-toggle>Show JSON</button>
            ${jsonSections}
          ` : ""}
        </section>
      `;
    }

    function renderResults(payload) {
      renderErrors(payload.database_errors);
      currentPage = Number(payload.page || 1);
      resultTitleEl.innerHTML = `Found <strong>${esc(payload.total ?? payload.count)}</strong> jobs`;
      renderPagination(payload);
      if (!payload.results.length) {
        resultsEl.innerHTML = '<div class="empty">No vacancies match these filters.</div>';
        return;
      }
      resultsEl.innerHTML = payload.results.map((job, index) => {
        const initial = String(job.company || job.title || "?").trim().slice(0, 1) || "?";
        const detailsId = makeDomId("job-details", job.id, index);
        const tags = [
          job.role ? `<span class="tag role">${esc(job.role)}</span>` : "",
          job.seniority ? `<span class="tag warn">${esc(job.seniority)}</span>` : "",
          job.remote_mode ? `<span class="tag">${esc(job.remote_mode)}</span>` : "",
          ...job.matched_keywords.map((keyword) => `<span class="tag keyword">${esc(keyword)}</span>`),
          ...job.skills.map((skill) => `<span class="tag">${esc(skill)}</span>`)
        ].filter(Boolean).join("");
        return `
          <article class="job">
            <div class="job-head">
              <div class="company-mark" aria-hidden="true">${esc(initial)}</div>
              <div>
                <h2>${esc(job.title || "Untitled vacancy")}</h2>
                <div class="company">${esc(job.company || "-")}</div>
                <div class="meta">
                  <span>${esc(job.location || "-")}</span>
                  <span>${esc(job.source || "-")}</span>
                  <span>${esc(job.publication_date || job.last_seen_at || "-")}</span>
                </div>
              </div>
              <div class="job-side">
                <div class="salary">${esc(job.salary || "")}</div>
                <div class="job-actions">
                  <button class="details-toggle" type="button" aria-expanded="false" aria-controls="${detailsId}" data-details-target="${detailsId}">Details</button>
                  ${job.url ? `<a class="open-link" href="${esc(job.url)}" target="_blank" rel="noreferrer" title="Open original vacancy">Open</a>` : ""}
                </div>
              </div>
            </div>
            ${tags ? `<div class="tags">${tags}</div>` : ""}
            ${job.description_preview ? `<p class="preview">${esc(job.description_preview)}${job.description_preview.length >= 420 ? "..." : ""}</p>` : ""}
            ${renderJobDetails(job, detailsId)}
          </article>
        `;
      }).join("");
    }

    async function loadFacets() {
      addLog("Facets", "Loading local database facets.");
      const response = await fetch("/api/facets");
      const facets = await response.json();
      setOptions(document.querySelector("#source"), facets.sources || []);
      setOptions(document.querySelector("#role"), mergeFacetItems([
        ...(facets.terms?.role_family_primary || []),
        ...(facets.terms?.role_family || [])
      ]));
      setOptions(document.querySelector("#seniority"), facets.terms?.seniority || []);
      setOptions(document.querySelector("#location"), facets.locations || []);
      setDatalist("#skill-list", mergeFacetItems([
        ...(facets.terms?.programming_language || []),
        ...(facets.terms?.framework_library || []),
        ...(facets.terms?.cloud_platform || []),
        ...(facets.terms?.database || []),
        ...(facets.terms?.tool || [])
      ]));
      setDatalist("#keyword-list", mergeFacetItems([
        ...(facets.terms?.programming_language || []),
        ...(facets.terms?.framework_library || []),
        ...(facets.terms?.cloud_platform || []),
        ...(facets.terms?.database || []),
        ...(facets.terms?.tool || []),
        ...(facets.terms?.methodology || [])
      ]));
      subtitleEl.textContent = `${facets.total || 0} local vacancies across ${(facets.databases || []).length} database(s).`;
      databaseSummaryEl.innerHTML = renderSummaryBlock("Sources", facets.sources || []);
      renderErrors(facets.database_errors);
      addLog("Facets", `Loaded ${facets.total || 0} vacancies across ${(facets.databases || []).length} database(s).`, facets.database_errors?.length ? "warning" : "success");
    }

    async function runSearch(page = currentPage) {
      addLog("Vacancy Search", `Searching local databases, page ${page}.`);
      resultsEl.innerHTML = '<div class="empty">Searching local databases...</div>';
      paginationEl.innerHTML = "";
      const response = await fetch(`/api/search?${buildParams(page).toString()}`);
      const payload = await response.json();
      if (!response.ok) {
        resultsEl.innerHTML = `<div class="error">${esc(payload.error || "Search failed")}</div>`;
        addLog("Vacancy Search", payload.error || "Search failed.", "error");
        return;
      }
      renderResults(payload);
      addLog("Vacancy Search", `Found ${payload.total ?? payload.count ?? 0} matching vacancies.`, payload.database_errors?.length ? "warning" : "success");
    }

    menuButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const view = button.dataset.viewTarget;
        if (!view || view === currentView) return;
        setView(view);
      });
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      setView("vacancies");
      currentPage = 1;
      runSearch(1);
    });
    resetBtn.addEventListener("click", () => {
      form.reset();
      syncSalaryInputsFromRange();
      currentPage = 1;
      addLog("Vacancy Search", "Cleared search filters.");
      runSearch(1);
    });
    paginationEl.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-page]");
      if (!button || button.disabled) return;
      const page = Number(button.dataset.page);
      if (!Number.isFinite(page)) return;
      runSearch(page);
    });
    resultsEl.addEventListener("click", (event) => {
      const jsonButton = event.target.closest("button[data-json-toggle]");
      if (jsonButton) {
        const panel = jsonButton.closest(".job-details-panel");
        const sections = panel ? Array.from(panel.querySelectorAll(".json-section")) : [];
        const isExpanded = jsonButton.getAttribute("aria-expanded") === "true";
        jsonButton.setAttribute("aria-expanded", String(!isExpanded));
        jsonButton.textContent = isExpanded ? "Show JSON" : "Hide JSON";
        sections.forEach((section) => {
          section.hidden = isExpanded;
        });
        return;
      }

      const button = event.target.closest("button[data-details-target]");
      if (button) {
        const panel = document.getElementById(button.dataset.detailsTarget);
        if (!panel) return;
        const isExpanded = button.getAttribute("aria-expanded") === "true";
        button.setAttribute("aria-expanded", String(!isExpanded));
        button.textContent = isExpanded ? "Details" : "Hide details";
        panel.hidden = isExpanded;
        const preview = button.closest(".job")?.querySelector(".preview");
        if (preview) {
          preview.hidden = !isExpanded;
        }
      }
    });
    salaryMinRange.addEventListener("input", () => syncSalaryInputsFromRange("min"));
    salaryMaxRange.addEventListener("input", () => syncSalaryInputsFromRange("max"));
    salaryMinInput.addEventListener("input", syncSalaryRangeFromInputs);
    salaryMaxInput.addEventListener("input", syncSalaryRangeFromInputs);

    document.querySelector("#parser-workspace .btn.primary")?.addEventListener("click", () => {
      startParserRun();
    });
    document.querySelector("#parser-workspace .btn.secondary")?.addEventListener("click", () => {
      const payload = collectParserPayload();
      const args = [
        payload.mode ? `--mode ${payload.mode}` : "",
        payload.canton ? `--canton ${payload.canton}` : "",
        payload.term ? `--term ${payload.term}` : "",
        payload.location ? `--location ${payload.location}` : "",
        payload.max_pages ? `--max-pages ${payload.max_pages}` : "",
        payload.detail_limit ? `--detail-limit ${payload.detail_limit}` : "",
      ].filter(Boolean).join(" ");
      const sourceText = payload.sources.length ? payload.sources.join(", ") : "no sources selected";
      addLog("Vacancy Collection", `Preview for ${sourceText}: python -m swiss_jobs.cli.parse --source <source> ${args}`.trim(), "info");
      setLogDrawer(true);
    });
    document.querySelector("#ai-analyse-workspace .btn.primary")?.addEventListener("click", () => {
      startAiAnalysisRun();
    });
    document.querySelector("#ai-analyse-workspace .btn.secondary")?.addEventListener("click", () => {
      const payload = collectAiAnalysisPayload();
      const args = [
        `--model ${payload.model}`,
        payload.first_seen_from ? `--first-seen-from ${payload.first_seen_from}` : "",
        payload.first_seen_to ? `--first-seen-to ${payload.first_seen_to}` : "",
        payload.scope === "all selected vacancies" ? "--include-analyzed" : "",
        payload.scope === "all selected vacancies" && !payload.limit ? "--all" : "",
        payload.limit ? `--limit ${payload.limit}` : "",
      ].filter(Boolean).join(" ");
      const sourceText = payload.sources.length ? payload.sources.join(", ") : "no sources selected";
      addLog("AI Analyse", `Preview for ${sourceText}: python -m swiss_jobs.cli.analyze_vacancies_llm --source <source> ${args}`.trim(), "info");
      setLogDrawer(true);
    });
    document.querySelector("#public-stats-workspace .btn.primary")?.addEventListener("click", () => {
      startPublicStatsRun();
    });
    document.querySelector("#public-stats-workspace .btn.secondary")?.addEventListener("click", () => {
      const payload = collectPublicStatsPayload();
      const sourceText = payload.sources.length ? payload.sources.join(", ") : "no sources selected";
      addLog(
        "Public Stats",
        `Preview for ${sourceText}: export analytics${payload.salary_group_minimum ? ` with salary groups >= ${payload.salary_group_minimum}` : ""} -> build ${payload.output_dir}/data + ${payload.output_dir}/csv${payload.snapshot_date ? ` for ${payload.snapshot_date}` : ""} -> sync ${payload.site_dir}.`,
        "info",
      );
      setLogDrawer(true);
    });
    openAiSettingsFormEl.addEventListener("submit", (event) => {
      event.preventDefault();
      saveOpenAiSettings();
    });
    logToggleEl.addEventListener("click", () => {
      setLogDrawer(logToggleEl.getAttribute("aria-expanded") !== "true");
    });
    logCloseEl.addEventListener("click", () => setLogDrawer(false));
    logClearEl.addEventListener("click", () => {
      logs.length = 0;
      renderLogs();
      addLog("Logs", "Log history cleared.");
    });

    syncSalaryTrack();
    renderLogs();
    addLog("Application", "Local vacancy interface initialized.");
    loadFacets().then(runSearch).catch((error) => {
      resultsEl.innerHTML = `<div class="error">${esc(error.message || error)}</div>`;
      addLog("Application", error.message || String(error), "error");
    });
