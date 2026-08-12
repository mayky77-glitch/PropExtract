(() => {
  "use strict";

  const root = document.documentElement;
  const themeButtons = [...document.querySelectorAll("[data-theme-choice]")];
  const preferredTheme = window.matchMedia("(prefers-color-scheme: dark)");
  let savedTheme = localStorage.getItem("propextract-theme") || "auto";
  if (!["auto", "light", "dark"].includes(savedTheme)) savedTheme = "auto";
  root.dataset.theme = savedTheme;
  const syncThemeButtons = () => {
    const visibleTheme = savedTheme === "auto" ? (preferredTheme.matches ? "dark" : "light") : savedTheme;
    themeButtons.forEach(button => button.setAttribute("aria-pressed", String(button.dataset.themeChoice === visibleTheme)));
  };
  syncThemeButtons();
  preferredTheme.addEventListener("change", syncThemeButtons);
  themeButtons.forEach(button => {
    button.addEventListener("click", () => {
      savedTheme = button.dataset.themeChoice;
      root.dataset.theme = savedTheme;
      localStorage.setItem("propextract-theme", savedTheme);
      syncThemeButtons();
    });
  });

  const toast = document.querySelector("#toast");
  const shutdownScreen = document.querySelector("#shutdown-screen");
  let toastTimer = null;

  function showToast(message, duration = 3500) {
    if (!toast) return;
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.hidden = false;
    toastTimer = window.setTimeout(() => { toast.hidden = true; }, duration);
  }

  async function responseJson(response) {
    try {
      return await response.json();
    } catch (_) {
      throw new Error("Сервер вернул некорректный ответ.");
    }
  }

  document.querySelectorAll("[data-shutdown]").forEach(button => {
    button.addEventListener("click", async () => {
      if (!window.confirm("Остановить PropExtract? Во время следующего запуска нужно будет открыть файл «Запустить PropExtract.cmd».")) return;
      button.disabled = true;
      try {
        const response = await fetch("/api/shutdown", {
          method: "POST",
          headers: {"Content-Type": "application/json", "X-PropExtract-Action": "shutdown"},
          body: "{}"
        });
        const payload = await responseJson(response);
        if (!response.ok) throw new Error(payload.error || "Не удалось остановить программу");
        if (shutdownScreen) shutdownScreen.hidden = false;
      } catch (error) {
        button.disabled = false;
        showToast("Не удалось остановить PropExtract. Повторите попытку.", 6000);
      }
    });
  });

  const form = document.querySelector("#import-form");
  if (!form) return;

  const startButton = document.querySelector("#start-button");
  const progressPanel = document.querySelector("#progress-panel");
  const progressTitle = document.querySelector("#progress-title");
  const progressValue = document.querySelector("#progress-value");
  const progressTrack = document.querySelector(".progress-track");
  const progressFill = document.querySelector("#progress-fill");
  const currentFile = document.querySelector("#current-file");
  const systemState = document.querySelector("#system-state");
  const result = document.querySelector("#result");
  const resultTitle = document.querySelector("#result-title");
  const resultBadge = document.querySelector("#result-badge");
  const resultStats = document.querySelector("#result-stats");
  const resultPaths = document.querySelector("#result-paths");
  const resultRows = document.querySelector("#result-rows");
  const rulerSteps = [...document.querySelectorAll(".process-ruler li")];
  let pollTimer = null;

  const escapeText = (value) => String(value ?? "").replace(/[&<>"']/g, char => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"})[char]);

  const sourceName = (item, documents) => {
    const document = documents[item.document_id] || {};
    return item.filename || document.filename || "PDF";
  };

  const openDocumentButton = item => item.document_id
    ? `<button class="row-action row-action--secondary" type="button" data-open-document="${escapeText(item.document_id)}">Открыть PDF</button>`
    : "";

  function recordHeader(item, status, tone) {
    return `<div class="record-card-heading"><div><span class="record-label">РНС</span><h4>${escapeText(item.number || "Не определён")}</h4></div><span class="record-status record-status--${tone}">${status}</span></div>`;
  }

  function rowMarker(row) {
    return `<div class="sheet-row-marker" aria-label="Строка Excel ${escapeText(row ?? "не определена")}"><span>Строка</span><strong>${escapeText(row ?? "—")}</strong></div>`;
  }

  function recordSource(item, documents) {
    return `<div class="record-source"><span class="record-label">Источник PDF</span><strong>${escapeText(sourceName(item, documents))}</strong></div>`;
  }

  function renderProposalCard(item, documents) {
    const approved = item.status === "approved";
    const unresolvedReview = Boolean(item.review_details);
    const tone = approved && !unresolvedReview ? "approved" : "review";
    const comparisonLabel = approved ? "Перенесено в таблицу" : "Предлагаемое изменение";
    const existingLabel = approved ? "Было" : "В таблице";
    const proposedLabel = approved ? "Перенесено" : "В документе";
    const status = approved && unresolvedReview
      ? "Поле перенесено — нужна проверка"
      : approved ? "Перенесено" : "Требует решения";
    return `<article class="record-card record-card--${tone}">
      ${rowMarker(item.row)}
      <div class="record-card-main">
        ${recordHeader(item, status, tone)}
        <p class="record-object">${escapeText(item.object || "Данные документа отличаются от таблицы.")}</p>
        ${item.review_details ? `<div class="record-verdict record-verdict--review"><strong>Связанные документы требуют проверки</strong><span>${escapeText(item.review_details)}</span></div>` : ""}
        <div class="record-diff" aria-label="Сравнение поля ${escapeText(item.field)}">
          <div class="record-diff-heading"><span>${comparisonLabel}</span><strong>${escapeText(item.field)}</strong></div>
          <div class="record-diff-values">
            <div class="record-value record-value--existing"><span>${existingLabel}</span><strong>${escapeText(item.existing ?? "Не заполнено")}</strong></div>
            <span class="record-diff-arrow" aria-hidden="true">→</span>
            <div class="record-value record-value--proposed"><span>${proposedLabel}</span><strong>${escapeText(item.proposed ?? "Не заполнено")}</strong></div>
          </div>
        </div>
        <div class="record-card-footer">
          ${recordSource(item, documents)}
          <div class="row-actions">${openDocumentButton(item)}<button class="row-action row-action--primary" type="button" data-approve-proposal="${escapeText(item.id)}" ${approved ? "disabled" : ""}>${approved ? "Изменение перенесено" : "Перенести в таблицу"}</button></div>
        </div>
      </div>
    </article>`;
  }

  function renderMatchedCard(item, documents) {
    return `<article class="record-card record-card--matched">
      ${rowMarker(item.row)}
      <div class="record-card-main">
        ${recordHeader(item, "Совпадает", "matched")}
        ${item.object ? `<p class="record-object">${escapeText(item.object)}</p>` : ""}
        <div class="record-verdict"><strong>Данные уже есть в таблице</strong><span>Строка оставлена без изменений. При открытии Excel обновятся только родные цветовые маркеры сроков.</span></div>
        <div class="record-card-footer">${recordSource(item, documents)}<div class="row-actions">${openDocumentButton(item)}</div></div>
      </div>
    </article>`;
  }

  function renderProcessedCard(item, documents) {
    return `<article class="record-card record-card--processed">
      ${rowMarker(item.row)}
      <div class="record-card-main">
        ${recordHeader(item, "Обработано", "processed")}
        <p class="record-object">${escapeText(item.object || item.details || "Данные обработаны.")}</p>
        <div class="record-card-footer">${recordSource(item, documents)}<div class="row-actions">${openDocumentButton(item)}</div></div>
      </div>
    </article>`;
  }

  function renderReviewCard(item, documents) {
    return `<article class="record-card record-card--review">
      ${rowMarker(item.row)}
      <div class="record-card-main">
        ${recordHeader(item, "Требует проверки", "review")}
        ${item.object ? `<p class="record-object">${escapeText(item.object)}</p>` : ""}
        <div class="record-verdict record-verdict--review"><strong>Автоматический перенос ограничен</strong><span>${escapeText(item.details || "Строка содержит неоднозначные данные. Сверьте исходный PDF и таблицу.")}</span></div>
        <div class="record-card-footer">${recordSource(item, documents)}<div class="row-actions">${openDocumentButton(item)}</div></div>
      </div>
    </article>`;
  }

  function renderCardGroup(id, eyebrow, title, description, cards, tone) {
    if (!cards.length) return "";
    return `<section class="result-group result-group--${tone}" aria-labelledby="${id}">
      <div class="result-group-heading"><div><span>${eyebrow}</span><h3 id="${id}">${title}</h3><p>${description}</p></div><strong aria-label="Количество строк: ${cards.length}">${cards.length}</strong></div>
      <div class="result-card-list">${cards.join("")}</div>
    </section>`;
  }

  document.querySelectorAll("[data-picker-kind]").forEach(button => {
    button.addEventListener("click", async () => {
      const target = document.querySelector(`#${button.dataset.pickerTarget}`);
      const label = button.querySelector("span");
      const originalLabel = label?.textContent;
      const controller = new AbortController();
      const pickerTimeout = window.setTimeout(() => controller.abort(), 125000);
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      if (label) label.textContent = "Окно открыто";
      showToast("Окно выбора открывается поверх браузера. Если его не видно, проверьте панель задач Windows.", 7000);
      try {
        const response = await fetch("/api/picker", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({kind: button.dataset.pickerKind}),
          signal: controller.signal
        });
        const payload = await responseJson(response);
        if (!response.ok) throw new Error(payload.error || "Не удалось открыть окно выбора");
        if (payload.path) {
          target.value = payload.path;
          target.focus();
        }
      } catch (error) {
        showToast(error.name === "AbortError" ? "Окно выбора не ответило. Проверьте панель задач или вставьте путь вручную." : "Не удалось открыть окно выбора. Вставьте путь вручную или повторите попытку.", 7000);
      } finally {
        window.clearTimeout(pickerTimeout);
        button.disabled = false;
        button.removeAttribute("aria-busy");
        if (label && originalLabel) label.textContent = originalLabel;
      }
    });
  });

  function setProgress(job) {
    const value = Number(job.progress || 0);
    progressTitle.textContent = job.stage || "Обработка";
    progressValue.textContent = `${value}%`;
    progressFill.style.width = `${value}%`;
    progressTrack.setAttribute("aria-valuenow", value);
    currentFile.textContent = job.current_file || (job.status === "done" ? "Все проверки завершены." : "Подождите, операция выполняется локально.");
    const activeIndex = value < 80 ? 0 : value < 94 ? 1 : value < 98 ? 2 : 3;
    rulerSteps.forEach((step, index) => step.classList.toggle("active", job.status === "running" && index === activeIndex));
  }

  function renderResult(job) {
    result.hidden = false;
    const failed = job.status === "error";
    result.classList.toggle("error", failed);
    progressPanel.classList.toggle("error", failed);
    if (failed) {
      resultTitle.textContent = "Реестр не изменён";
      resultBadge.textContent = "Ошибка";
      resultStats.innerHTML = "";
      const phase = job.error_phase ? `<p><strong>Этап:</strong> ${escapeText(job.error_phase)}</p>` : "";
      const file = job.error_file ? `<p><strong>PDF:</strong> ${escapeText(job.error_file)}</p>` : "";
      const log = job.technical_log ? "<p>Технический журнал сохранён рядом с программой.</p>" : "";
      resultRows.innerHTML = "";
      resultPaths.innerHTML = `<p><strong>Причина:</strong> ${escapeText(job.error || "Не удалось завершить операцию.")}</p><p>${escapeText(job.error_hint || "Исправьте указанную причину и повторите запуск. Исходный Excel не изменён.")}</p>${phase}${file}${log}`;
      return;
    }
    const stats = job.summary || {};
    const allAlreadyPresent = Number(stats.record_count || 0) > 0
      && Number(stats.already_present_count || 0) === Number(stats.record_count || 0)
      && Number(stats.changed_rows || 0) === 0;
    resultTitle.textContent = allAlreadyPresent ? "Данные уже внесены" : "Реестр обновлён";
    resultBadge.textContent = allAlreadyPresent ? "Совпадают" : "Готово";
    const alreadyPresentRatio = `${Number(stats.already_present_count || 0)} из ${Number(stats.record_count || 0)}`;
    const statItems = [
      [stats.pdf_count, "PDF обработано"],
      [alreadyPresentRatio, "Уже были в реестре"],
      [stats.new_rows, "Новых строк"],
      [stats.issue_count ?? stats.conflicts, "Замечаний в Excel"]
    ];
    if (stats.failed_pdf_count) statItems.push([stats.failed_pdf_count, "PDF пропущено"]);
    resultStats.innerHTML = statItems.map(([number, label]) => `<div class="stat"><strong>${escapeText(number ?? 0)}</strong><span>${label}</span></div>`).join("");
    const rows = (stats.row_numbers || []).join(", ") || "нет";
    const newRows = (stats.new_row_numbers || []).join(", ") || "нет";
    const issueRows = (stats.rows_with_issues || []).join(", ") || "нет";
    resultPaths.innerHTML = `<p><strong>Обработанные строки Excel:</strong> ${escapeText(rows)}</p><p><strong>Добавленные строки Excel:</strong> ${escapeText(newRows)}</p><p><strong>Строки со статусом:</strong> ${escapeText(issueRows)}</p>${job.warning ? `<p><strong>Предупреждение:</strong> ${escapeText(job.warning)}</p>` : ""}`;
    const documents = Object.fromEntries((job.documents || []).map(item => [item.id, item]));
    const proposalRows = new Set((job.proposals || []).map(item => `${item.row ?? ""}::${item.number || ""}`));
    const reviewCards = [
      ...(job.proposals || []).filter(item => item.status !== "approved" || item.review_details).map(item => renderProposalCard(item, documents)),
      ...(job.row_cards || [])
        .filter(item => item.needs_review && !proposalRows.has(`${item.row ?? ""}::${item.number || ""}`))
        .map(item => renderReviewCard(item, documents))
    ];
    const approvedCards = (job.proposals || []).filter(item => item.status === "approved" && !item.review_details).map(item => renderProposalCard(item, documents));
    const processedCards = (job.row_cards || [])
      .filter(item => item.outcome !== "already_present" && !item.needs_review && !proposalRows.has(`${item.row ?? ""}::${item.number || ""}`))
      .map(item => renderProcessedCard(item, documents));
    const matchedCards = (job.row_cards || []).filter(item => item.outcome === "already_present").map(item => renderMatchedCard(item, documents));
    resultRows.innerHTML = [
      renderCardGroup("review-group-title", "Нужно ваше решение", "Строки для проверки", "Сверьте исходный PDF с таблицей и переносите только подтверждённые предложения.", reviewCards, "review"),
      renderCardGroup("matched-group-title", "Без изменений", "Уже заполнены", "Данные PDF совпадают с реестром. Можно открыть исходный файл для проверки.", matchedCards, "matched"),
      renderCardGroup("approved-group-title", "Одобрено", "Изменения перенесены", "Для каждого изменения создана проверенная резервная копия.", approvedCards, "approved"),
      renderCardGroup("processed-group-title", "Готово", "Обработанные строки", "Данные перенесены и проверены.", processedCards, "processed")
    ].join("");
  }

  resultRows?.addEventListener("click", async event => {
    const button = event.target.closest("button");
    if (!button || !window.currentPropExtractJob) return;
    const job = window.currentPropExtractJob;
    const documentId = button.dataset.openDocument;
    const proposalId = button.dataset.approveProposal;
    if (!documentId && !proposalId) return;
    button.disabled = true;
    try {
      const suffix = documentId ? `/documents/${encodeURIComponent(documentId)}/open` : `/proposals/${encodeURIComponent(proposalId)}/approve`;
      const response = await fetch(`/api/jobs/${encodeURIComponent(job.id)}${suffix}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({capability: job.capability})});
      const payload = await responseJson(response);
      if (!response.ok) throw new Error(payload.error || "Не удалось выполнить действие");
      if (proposalId) { showToast("Изменение перенесено. Резервная копия создана."); poll(job.id); }
      else showToast("Открываем исходный PDF.");
    } catch (error) { button.disabled = false; showToast("Не удалось выполнить действие. Обновите результат и повторите попытку.", 6000); }
  });

  async function poll(jobId) {
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, {cache: "no-store"});
      const job = await responseJson(response);
      if (!response.ok) throw new Error(job.error || "Не удалось получить состояние");
      setProgress(job);
      window.currentPropExtractJob = job;
      if (job.status === "done" || job.status === "error") {
        startButton.disabled = false;
        renderResult(job);
        return;
      }
      pollTimer = window.setTimeout(() => poll(jobId), 700);
    } catch (error) {
      startButton.disabled = false;
      renderResult({status: "error", error: "Не удалось получить состояние операции.", error_hint: "Проверьте подключение к PropExtract и повторите запуск."});
    }
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    window.clearTimeout(pollTimer);
    result.hidden = true;
    result.classList.remove("error");
    progressPanel.classList.remove("error");
    startButton.disabled = true;
    setProgress({progress: 1, stage: "Отправляем задачу", status: "running"});
    const payload = Object.fromEntries(new FormData(form).entries());
    try {
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      const job = await responseJson(response);
      if (!response.ok) throw new Error(job.error || "Не удалось запустить импорт");
      poll(job.id);
    } catch (error) {
      startButton.disabled = false;
      setProgress({progress: 0, stage: "Запуск остановлен", status: "error"});
      renderResult({status: "error", error: "Не удалось запустить импорт.", error_hint: "Проверьте подключение к PropExtract и параметры запуска."});
    }
  });

  fetch("/api/system", {cache: "no-store"})
    .then(responseJson)
    .then(state => {
      systemState.className = `system-state ${state.ready ? "ready" : "error"}`;
      systemState.querySelector("span:last-child").textContent = state.ready
        ? "OCR-компоненты готовы"
        : "Не хватает Tesseract, Poppler или языков rus+eng — откройте инструкцию";
    })
    .catch(() => {
      systemState.className = "system-state error";
      systemState.querySelector("span:last-child").textContent = "Не удалось проверить OCR-компоненты";
    });
})();
