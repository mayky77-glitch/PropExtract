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

  function publicFailure(payload, fallback, fallbackHint = "") {
    const error = typeof payload?.error === "string" && payload.error.trim() ? payload.error.trim() : fallback;
    const hint = typeof payload?.hint === "string" && payload.hint.trim() ? payload.hint.trim() : fallbackHint;
    return {error, hint};
  }

  function publicFailureText(payload, fallback, fallbackHint = "") {
    const {error, hint} = publicFailure(payload, fallback, fallbackHint);
    return hint ? `${error} ${hint}` : error;
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
        if (!response.ok) {
          showToast(publicFailureText(payload, "Не удалось остановить PropExtract. Повторите попытку."), 6000);
          button.disabled = false;
          return;
        }
        if (shutdownScreen) shutdownScreen.hidden = false;
      } catch (_) {
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
  const editableFieldKeys = new Set(["type", "stage", "object", "issue", "end", "changed", "issuer", "builder", "region", "district", "developer"]);
  const dateFieldKeys = new Set(["issue", "end", "changed"]);
  const manuallyResolvedStatuses = new Set(["resolved", "resolved_manual"]);

  const sourceName = (item, documents) => {
    const document = documents[item.document_id] || {};
    return item.filename || document.filename || "PDF";
  };

  const openDocumentButton = item => item.document_id
    ? `<button class="row-action row-action--secondary" type="button" data-open-document="${escapeText(item.document_id)}">Открыть PDF</button>`
    : "";

  function editableFields(item) {
    if (typeof item.edit_id !== "string" || !item.edit_id) return [];
    return (Array.isArray(item.editable_fields) ? item.editable_fields : [])
      .filter(field => field && editableFieldKeys.has(field.key) && typeof field.label === "string" && field.label)
      .map(field => ({...field, value: String((item.editable_values || {})[field.key] ?? "")}));
  }

  function renderEditControls(item) {
    const fields = editableFields(item);
    if (!fields.length) return "";
    const inputs = fields.map(field => {
      const isDate = dateFieldKeys.has(field.key);
      return `<label class="row-edit-field"><span>${escapeText(field.label)}</span><input data-edit-input data-field-key="${escapeText(field.key)}" data-initial-value="${escapeText(field.value)}" value="${escapeText(field.value)}" type="text"${isDate ? " inputmode=\"numeric\" placeholder=\"дд.мм.гггг\"" : ""} autocomplete="off"></label>`;
    }).join("");
    return `<div class="row-edit-wrap">
      <button class="row-action row-action--edit" type="button" data-edit-toggle="${escapeText(item.edit_id)}" aria-expanded="false">Исправить данные</button>
      <form class="row-edit-form" data-row-edit-form="${escapeText(item.edit_id)}" hidden novalidate>
        <div class="row-edit-heading"><div><span class="record-label">Корректировка строки</span><h5>Исправить данные</h5></div><p>Измените только нужные сведения. Номер РНС и служебные столбцы не редактируются.</p></div>
        <p class="row-edit-date-hint">Даты указывайте в формате дд.мм.гггг.</p>
        <div class="row-edit-grid">${inputs}</div>
        <p class="row-edit-feedback" data-edit-feedback role="status" aria-live="polite"></p>
        <div class="row-edit-actions"><button class="row-action row-action--secondary" type="button" data-edit-cancel>Отмена</button><button class="row-action row-action--primary" type="submit" data-edit-save>Сохранить исправления</button></div>
      </form>
    </div>`;
  }

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
    const resolved = manuallyResolvedStatuses.has(item.status);
    const canApprove = typeof item.id === "string" && item.id && item.status === "pending" && Boolean(item.action);
    const unresolvedReview = Boolean(item.review_details);
    const tone = (approved || resolved) && !unresolvedReview ? "approved" : "review";
    const comparisonLabel = approved ? "Перенесено в таблицу" : resolved ? "Исправлено вручную" : "Предлагаемое изменение";
    const existingLabel = approved || resolved ? "Было" : "В таблице";
    const proposedLabel = approved ? "Перенесено" : resolved ? "Исправлено" : "В документе";
    const displayedValue = resolved ? item.manual_value : item.proposed;
    const status = resolved ? "Исправлено вручную" : approved && unresolvedReview
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
            <div class="record-value record-value--proposed"><span>${proposedLabel}</span><strong>${escapeText(displayedValue ?? "Не заполнено")}</strong></div>
          </div>
        </div>
        <div class="record-card-footer">
          ${recordSource(item, documents)}
          <div class="row-actions">${openDocumentButton(item)}${canApprove ? `<button class="row-action row-action--primary" type="button" data-approve-proposal="${escapeText(item.id)}">Перенести в таблицу</button>` : ""}${resolved ? `<span class="row-action row-action--resolved" aria-label="Исправлено вручную">Исправлено вручную</span>` : ""}${renderEditControls(item)}</div>
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
        <div class="record-card-footer">${recordSource(item, documents)}<div class="row-actions">${openDocumentButton(item)}${renderEditControls(item)}</div></div>
      </div>
    </article>`;
  }

  function renderProcessedCard(item, documents) {
    return `<article class="record-card record-card--processed">
      ${rowMarker(item.row)}
      <div class="record-card-main">
        ${recordHeader(item, "Обработано", "processed")}
        <p class="record-object">${escapeText(item.object || item.details || "Данные обработаны.")}</p>
        <div class="record-card-footer">${recordSource(item, documents)}<div class="row-actions">${openDocumentButton(item)}${renderEditControls(item)}</div></div>
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
        <div class="record-card-footer">${recordSource(item, documents)}<div class="row-actions">${openDocumentButton(item)}${renderEditControls(item)}</div></div>
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
        if (!response.ok) {
          showToast(publicFailureText(payload, "Не удалось открыть окно выбора. Вставьте путь вручную или повторите попытку."), 7000);
          return;
        }
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
    const unchangedReview = job.published === false && !allAlreadyPresent;
    resultTitle.textContent = allAlreadyPresent ? "Данные уже внесены" : unchangedReview ? "Реестр не изменён" : "Реестр обновлён";
    resultBadge.textContent = allAlreadyPresent ? "Совпадают" : unchangedReview ? "Без изменений" : "Готово";
    const alreadyPresentRatio = `${Number(stats.already_present_count || 0)} из ${Number(stats.record_count || 0)}`;
    const statItems = [
      [stats.pdf_count, "PDF обработано"],
      [alreadyPresentRatio, "Уже были в реестре"],
      [stats.new_rows, "Новых строк"],
      [stats.issue_count ?? stats.conflicts, "Замечаний в Excel"]
    ];
    const hasTypedDocumentCounts = ["out_of_scope_count", "unidentified_permit_count", "processing_failed_count"]
      .some(key => Object.hasOwn(stats, key));
    if (stats.out_of_scope_count) statItems.push([stats.out_of_scope_count, "Не относятся к РНС"]);
    const attentionCount = hasTypedDocumentCounts
      ? Number(stats.unidentified_permit_count || 0) + Number(stats.processing_failed_count || 0)
      : Number(stats.failed_pdf_count || 0);
    if (attentionCount) statItems.push([attentionCount, "Требуют внимания"]);
    resultStats.innerHTML = statItems.map(([number, label]) => `<div class="stat"><strong>${escapeText(number ?? 0)}</strong><span>${label}</span></div>`).join("");
    const rows = (stats.row_numbers || []).join(", ") || "нет";
    const newRows = (stats.new_row_numbers || []).join(", ") || "нет";
    const issueRows = (stats.rows_with_issues || []).join(", ") || "нет";
    resultPaths.innerHTML = `<p><strong>Обработанные строки Excel:</strong> ${escapeText(rows)}</p><p><strong>Добавленные строки Excel:</strong> ${escapeText(newRows)}</p><p><strong>Строки со статусом:</strong> ${escapeText(issueRows)}</p>${job.warning ? `<p><strong>Предупреждение:</strong> ${escapeText(job.warning)}</p>` : ""}`;
    const documents = Object.fromEntries((job.documents || []).map(item => [item.id, item]));
    const proposalRows = new Set((job.proposals || []).map(item => `${item.row ?? ""}::${item.number || ""}`));
    const editableCards = new Map((job.row_cards || [])
      .filter(item => editableFields(item).length)
      .map(item => [`${item.row ?? ""}::${item.number || ""}`, item]));
    const renderedEditRows = new Set();
    const renderProposal = item => {
      const key = `${item.row ?? ""}::${item.number || ""}`;
      const rowCard = editableCards.get(key);
      if (!rowCard || renderedEditRows.has(key)) return renderProposalCard(item, documents);
      renderedEditRows.add(key);
      return renderProposalCard({...item, edit_id: rowCard.edit_id, editable_fields: rowCard.editable_fields, editable_values: rowCard.editable_values}, documents);
    };
    const reviewCards = [
      ...(job.proposals || []).filter(item => item.review_details || (item.status !== "approved" && !manuallyResolvedStatuses.has(item.status))).map(renderProposal),
      ...(job.row_cards || [])
        .filter(item => item.needs_review && !proposalRows.has(`${item.row ?? ""}::${item.number || ""}`))
        .map(item => renderReviewCard(item, documents))
    ];
    const approvedCards = [
      ...(job.proposals || []).filter(item => item.status === "approved" && !item.review_details).map(renderProposal),
      ...(job.proposals || []).filter(item => manuallyResolvedStatuses.has(item.status) && !item.review_details).map(renderProposal)
    ];
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
    const editId = button.dataset.editToggle;
    if (editId) {
      const wrap = button.closest(".row-edit-wrap");
      const editForm = wrap?.querySelector("[data-row-edit-form]");
      if (!editForm) return;
      const expanded = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", String(!expanded));
      editForm.hidden = expanded;
      if (!expanded) window.requestAnimationFrame(() => editForm.querySelector("[data-edit-input]")?.focus());
      return;
    }
    if (button.hasAttribute("data-edit-cancel")) {
      const editForm = button.closest("form");
      const toggle = editForm?.closest(".row-edit-wrap")?.querySelector("[data-edit-toggle]");
      editForm?.reset();
      if (editForm) editForm.querySelector("[data-edit-feedback]").textContent = "";
      if (toggle) toggle.setAttribute("aria-expanded", "false");
      if (editForm) editForm.hidden = true;
      toggle?.focus();
      return;
    }
    if (!documentId && !proposalId) return;
    button.disabled = true;
    try {
      const suffix = documentId ? `/documents/${encodeURIComponent(documentId)}/open` : `/proposals/${encodeURIComponent(proposalId)}/approve`;
      const response = await fetch(`/api/jobs/${encodeURIComponent(job.id)}${suffix}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({capability: job.capability})});
      const payload = await responseJson(response);
      if (!response.ok) {
        button.disabled = false;
        showToast(publicFailureText(payload, "Не удалось выполнить действие. Обновите результат и повторите попытку."), 6000);
        return;
      }
      if (proposalId) { showToast("Изменение перенесено. Резервная копия создана."); poll(job.id); }
      else showToast("Открываем исходный PDF.");
    } catch (error) { button.disabled = false; showToast("Не удалось выполнить действие. Обновите результат и повторите попытку.", 6000); }
  });

  resultRows?.addEventListener("submit", async event => {
    const editForm = event.target.closest("[data-row-edit-form]");
    if (!editForm || !window.currentPropExtractJob) return;
    event.preventDefault();
    const fields = {};
    editForm.querySelectorAll("[data-edit-input]").forEach(input => {
      if (input.value !== input.dataset.initialValue) fields[input.dataset.fieldKey] = input.value;
    });
    const feedback = editForm.querySelector("[data-edit-feedback]");
    if (!Object.keys(fields).length) {
      feedback.textContent = "Нет изменений для сохранения.";
      return;
    }
    const saveButton = editForm.querySelector("[data-edit-save]");
    const cancelButton = editForm.querySelector("[data-edit-cancel]");
    const job = window.currentPropExtractJob;
    saveButton.disabled = true;
    cancelButton.disabled = true;
    editForm.setAttribute("aria-busy", "true");
    feedback.textContent = "Сохраняем исправления…";
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(job.id)}/edits/${encodeURIComponent(editForm.dataset.rowEditForm)}`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({capability: job.capability, fields})
      });
      const updatedJob = await responseJson(response);
      if (!response.ok) {
        feedback.textContent = publicFailureText(updatedJob, "Не удалось сохранить исправления. Проверьте данные и повторите попытку.");
        saveButton.disabled = false;
        cancelButton.disabled = false;
        editForm.removeAttribute("aria-busy");
        return;
      }
      window.currentPropExtractJob = updatedJob;
      renderResult(updatedJob);
      showToast("Исправления сохранены.");
    } catch (_) {
      feedback.textContent = "Не удалось сохранить исправления. Проверьте данные и повторите попытку.";
      saveButton.disabled = false;
      cancelButton.disabled = false;
      editForm.removeAttribute("aria-busy");
    }
  });

  async function poll(jobId) {
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, {cache: "no-store"});
      const job = await responseJson(response);
      if (!response.ok) throw new Error("Не удалось получить состояние");
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
      if (!response.ok) {
        const failure = publicFailure(job, "Не удалось запустить импорт.", "Проверьте подключение к PropExtract и параметры запуска.");
        startButton.disabled = false;
        setProgress({progress: 0, stage: "Запуск остановлен", status: "error"});
        renderResult({status: "error", error: failure.error, error_hint: failure.hint});
        return;
      }
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
