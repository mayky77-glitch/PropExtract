---
type: guide
status: ready
work_id: construction-group-routing-v1
role: integration
owner: integration-owner
last_verified: 2026-08-18
updated: 2026-08-18
tags:
  - task/planning
  - status/ready
  - domain/reliability
  - knowledge/windows
links:
  - "[[orda-construction-group-routing-plan]]"
  - "[[orda-construction-group-routing-waves]]"
  - "[[orda-middle-row-insertion-plan]]"
---

# Контракт ошибок и fallback

## Owner decision

Silent/dead-end fallback запрещён в новом flow и затронутых critical paths PDF/OCR → routing → XLSX → report/history. Исключение, timeout, unsupported state или исчерпанный retry не могут превращаться в `success`, `no-op`, empty result или продолжение с непомеченными неполными данными.

Независимые PDF можно продолжать обрабатывать, только если failed document имеет явную карточку, stable code/hint и correlated technical event.

## Разрешённые исходы

Каждая fallback-ветка заканчивается одним из двух доказуемых исходов:

1. `recovered` — работоспособность восстановлена, операция прошла тот же business/XLSX/formula oracle и вернула полный корректный результат. Причина и факт recovery записаны в technical log.
2. typed failure — админка показывает краткую русскую причину, что не выполнено, безопасный следующий шаг, error code, operation/job ID и наличие/место technical log.

Если XLSX уже на exact post-hash, UI сообщает «изменение применено, завершается восстановление отчёта/истории» и запрещает повторную вставку. Это recoverable finalization, не success и не retryable mutation.

## Technical record

Минимальные поля:

- timestamp, operation/job ID, component и exact stage;
- stable error code, exception class/message/traceback, HRESULT/WinError;
- pre/current/staged hashes, registry generation и journal phase;
- recovery decision, retry attempt count/last OS error и leased-process metadata;
- construction code, canonical RNS, target group/row-at-event-time без PDF/OCR body.

Public API/UI остаются sanitized; traceback и local paths не выходят из local technical log. Для installed Windows основной sink — `%LOCALAPPDATA%\PropExtract\logs\propextract-error.log`; portable build использует writable data-root. При отказе выполняется bounded запись в operation directory/`%TEMP%`. Двойной отказ становится user-visible `technical_log_unavailable`, target state остаётся доказуемым по journal/hash.

## Critical-path rules

- Запрещены `except: pass` и catch-and-continue в business/publication paths. Cleanup error присоединяется к исходному failure и не меняет его на success.
- Bounded retry заканчивается verified success либо typed failure; бесконечных повторов нет.
- Alternative path является recovery только после полного исходного oracle. Unsafe OpenPyXL/raw-OOXML insertion, запись в чужую группу и пропуск formula validation не являются fallback.
- Каждая typed failure имеет API/browser test, fault injection и проверку correlated record; тест также отвергает ложный success/no-op.
- Report/log finalization после verified XLSX publication не откатывает книгу, остаётся visible и завершается идемпотентно по operation ID.

## Required existing-path remediation

- Text-layer→raster OCR: trace сохраняет `text_layer_unavailable|timeout|nonzero|empty` и timings. Raster success — verified recovery; subsequent failure — item-scoped `processing_failed` + log.
- File-lock retry: после exhaustion сохраняются attempt count и последний исходный OS error.
- Report write, per-PDF processing, manual-edit preparation и stale/corrupt action-history: существующий warning/error сохраняется и получает structured technical event.
- New action/history identity: construction + canonical RNS + field/action + pre/post workbook hash + operation ID. Physical row — только coordinate at event time; перед действием row re-resolve-ится. Missing/ambiguous identity → stale warning/error + log.
- Excel COM: unavailable/open/insert/recalc/save/quit/validation failure не публикует candidate и не сообщает «строка добавлена»; post-hash finalization не запускает insertion повторно.

Cosmetic picker-topmost degradation и best-effort POSIX chmod не требуют remediation: они не скрывают failure основной операции и не влияют на Windows target.

## Acceptance matrix

- Fault injection на каждом new catch/retry/fallback: full-oracle `recovered` либо stable public error/code/hint + operation ID + correlated technical record.
- Primary log sink failure использует fallback sink; double sink failure явно виден как `technical_log_unavailable`.
- Successful retry сохраняет causal attempt metadata; exhausted retry сохраняет last original OS error.
- OCR raster recovery содержит typed text-layer cause без OCR/PDF content.
- Per-document failure не скрывает успешные независимые PDF и не становится empty success.
- Report failure после publication сообщает, что XLSX уже изменён, и recovery не создаёт вторую row/action.
- History/action после middle insert re-resolve-ится по construction+RNS; ambiguity не использует stale row.
- Cleanup/lease failure не закрывает user Excel и не маскирует исходный error.
