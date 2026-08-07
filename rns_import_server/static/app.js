(() => {
  "use strict";

  const root = document.documentElement;
  const themeSelect = document.querySelector("#theme-select");
  const savedTheme = localStorage.getItem("propextract-theme") || "auto";
  root.dataset.theme = savedTheme;
  if (themeSelect) {
    themeSelect.value = savedTheme;
    themeSelect.addEventListener("change", () => {
      root.dataset.theme = themeSelect.value;
      localStorage.setItem("propextract-theme", themeSelect.value);
    });
  }

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
      resultPaths.innerHTML = `<p><strong>Причина:</strong> ${escapeText(job.error || "Неизвестная ошибка")}</p><p>Проверьте пути, закройте Excel и повторите запуск.</p>`;
      return;
    }
    const stats = job.summary || {};
    resultStats.innerHTML = [
      [stats.pdf_count, "PDF обработано"],
      [stats.record_count, "Записей найдено"],
      [stats.changed_rows, "Строк обработано"],
      [stats.conflicts, "Конфликтов сохранено"]
    ].map(([number, label]) => `<div class="stat"><strong>${escapeText(number ?? 0)}</strong><span>${label}</span></div>`).join("");
    resultPaths.innerHTML = `<p><strong>Резервная копия:</strong> ${escapeText(job.backup)}</p>${job.report ? `<p><strong>Отчёт:</strong> ${escapeText(job.report)}</p>` : ""}${job.warning ? `<p><strong>Предупреждение:</strong> ${escapeText(job.warning)}</p>` : ""}`;
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
