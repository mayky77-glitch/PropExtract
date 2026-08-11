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
    const cards = [];
    const proposalRows = new Set((job.proposals || []).map(item => `${item.row ?? ""}::${item.number || ""}`));
    (job.proposals || []).forEach(item => {
      const document = documents[item.document_id] || {};
      const difference = item.status === "approved"
        ? `Перенесено «${escapeText(item.field)}»: «${escapeText(item.proposed)}».`
        : `${escapeText(item.field)}: в Excel «${escapeText(item.existing)}», в PDF «${escapeText(item.proposed)}».`;
      cards.push(`<article class="result-row ${item.status === "approved" ? "" : "conflict"}"><div><h3>Строка Excel ${escapeText(item.row ?? "не определена")} · РНС ${escapeText(item.number)}</h3><p>${escapeText(item.object || "Данные документа отличаются от таблицы.")}</p><p>${difference}</p><p>Источник: ${escapeText(item.filename || document.filename || "PDF")}</p></div><div class="row-actions">${item.document_id ? `<button class="row-action" type="button" data-open-document="${escapeText(item.document_id)}">Открыть PDF</button>` : ""}<button class="row-action" type="button" data-approve-proposal="${escapeText(item.id)}" ${item.status === "approved" ? "disabled" : ""}>${item.status === "approved" ? "Перенесено" : "Перенести изменения"}</button></div></article>`);
    });
    (job.row_cards || []).filter(item => item.outcome !== "already_present" && !proposalRows.has(`${item.row ?? ""}::${item.number || ""}`)).forEach(item => {
      const document = documents[item.document_id] || {};
      cards.push(`<article class="result-row"><div><h3>Строка Excel ${escapeText(item.row ?? "не определена")} · РНС ${escapeText(item.number)}</h3><p>${escapeText(item.object || item.details || "Данные обработаны.")}</p><p>Источник: ${escapeText(item.filename || document.filename || "PDF")}</p></div><div class="row-actions">${item.document_id ? `<button class="row-action" type="button" data-open-document="${escapeText(item.document_id)}">Открыть PDF</button>` : ""}</div></article>`);
    });
    (job.row_cards || []).filter(item => item.outcome === "already_present").forEach(item => {
      const document = documents[item.document_id] || {};
      cards.push(`<article class="result-row"><div><h3>Строка Excel ${escapeText(item.row)} · РНС ${escapeText(item.number)}</h3><p>Строка не изменена: данные уже есть в таблице.</p><p>При открытии Excel обновятся только родные цветовые маркеры сроков.</p><p>${escapeText(item.object || "")}</p><p>Источник: ${escapeText(item.filename || document.filename || "PDF")}</p></div><div class="row-actions">${item.document_id ? `<button class="row-action" type="button" data-open-document="${escapeText(item.document_id)}">Открыть PDF</button>` : ""}</div></article>`);
    });
    resultRows.innerHTML = cards.join("");
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
