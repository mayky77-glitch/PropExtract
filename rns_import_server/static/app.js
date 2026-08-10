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
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Не удалось остановить программу");
        if (shutdownScreen) shutdownScreen.hidden = false;
      } catch (error) {
        button.disabled = false;
        showToast(error.message, 6000);
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
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Не удалось открыть окно выбора");
        if (payload.path) {
          target.value = payload.path;
          target.focus();
        }
      } catch (error) {
        showToast(error.name === "AbortError" ? "Окно выбора не ответило. Проверьте панель задач или вставьте путь вручную." : error.message, 7000);
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
    resultTitle.textContent = failed ? "Реестр не изменён" : "Реестр обновлён";
    resultBadge.textContent = failed ? "Ошибка" : "Готово";
    if (failed) {
      resultStats.innerHTML = "";
      const phase = job.error_phase ? `<p><strong>Этап:</strong> ${escapeText(job.error_phase)}</p>` : "";
      const file = job.error_file ? `<p><strong>PDF:</strong> ${escapeText(job.error_file)}</p>` : "";
      const log = job.error_log ? `<p><strong>Технический журнал:</strong> ${escapeText(job.error_log)}</p>` : "";
      resultPaths.innerHTML = `<p><strong>Причина:</strong> ${escapeText(job.error || "Неизвестная ошибка")}</p><p>${escapeText(job.error_hint || "Исправьте указанную причину и повторите запуск. Исходный Excel не изменён.")}</p>${phase}${file}${log}`;
      return;
    }
    const stats = job.summary || {};
    resultStats.innerHTML = [
      [stats.pdf_count, "PDF обработано"],
      [stats.record_count, "Записей найдено"],
      [stats.new_rows, "Новых строк"],
      [stats.issue_count ?? stats.conflicts, "Замечаний в Excel"]
    ].map(([number, label]) => `<div class="stat"><strong>${escapeText(number ?? 0)}</strong><span>${label}</span></div>`).join("");
    const rows = (stats.row_numbers || []).join(", ") || "нет";
    const newRows = (stats.new_row_numbers || []).join(", ") || "нет";
    const issueRows = (stats.rows_with_issues || []).join(", ") || "нет";
    resultPaths.innerHTML = `<p><strong>Обработанные строки Excel:</strong> ${escapeText(rows)}</p><p><strong>Добавленные строки Excel:</strong> ${escapeText(newRows)}</p><p><strong>Строки со статусом:</strong> ${escapeText(issueRows)}</p><p><strong>Резервная копия:</strong> ${escapeText(job.backup)}</p>${job.report ? `<p><strong>Отчёт:</strong> ${escapeText(job.report)}</p>` : ""}${job.warning ? `<p><strong>Предупреждение:</strong> ${escapeText(job.warning)}</p>` : ""}`;
  }

  async function poll(jobId) {
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, {cache: "no-store"});
      const job = await response.json();
      if (!response.ok) throw new Error(job.error || "Не удалось получить состояние");
      setProgress(job);
      if (job.status === "done" || job.status === "error") {
        startButton.disabled = false;
        renderResult(job);
        return;
      }
      pollTimer = window.setTimeout(() => poll(jobId), 700);
    } catch (error) {
      startButton.disabled = false;
      renderResult({status: "error", error: error.message});
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
      const job = await response.json();
      if (!response.ok) throw new Error(job.error || "Не удалось запустить импорт");
      if (job.pdf_dir) document.querySelector("#pdf-dir").value = job.pdf_dir;
      if (job.xlsx) document.querySelector("#xlsx-path").value = job.xlsx;
      poll(job.id);
    } catch (error) {
      startButton.disabled = false;
      setProgress({progress: 0, stage: "Запуск остановлен", status: "error"});
      renderResult({status: "error", error: error.message});
    }
  });

  fetch("/api/system", {cache: "no-store"})
    .then(response => response.json())
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
