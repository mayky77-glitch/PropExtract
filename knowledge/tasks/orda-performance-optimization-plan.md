---
type: guide
status: ready
work_id: construction-group-performance-benchmark-v1
role: integration
owner: integration-owner
last_verified: 2026-08-18
updated: 2026-08-18
tags:
  - task/planning
  - status/ready
  - domain/performance
  - knowledge/windows
links:
  - "[[orda-construction-group-routing-plan]]"
  - "[[orda-construction-group-routing-waves]]"
  - "[[orda-middle-row-insertion-plan]]"
  - "[[../ORCHESTRATION|Orchestration]]"
---

# План Орды: Windows performance без регрессий

## Цель и жёсткие инварианты

После принятой функциональной интеграции уменьшить wall time, CPU, peak working set/RSS, лишние subprocess/disk reads и idle resource use на Windows. Результаты маршрутизации, РНС/name conflicts, proposals, Excel cells, no-op bytes, backups, report/API/UI semantics должны остаться эквивалентны exact functional baseline.

Стабильность важнее ускорения. Оптимизация не принимается, если её выигрыш не выходит за измеренный шум, если растёт другой критичный ресурс либо меняется functional oracle. Нулевой production diff — допустимый успешный исход профилирования.

## Проверенный lifecycle сейчас

- Tesseract и Poppler запускаются bounded `subprocess.run` и завершаются после вызова.
- OCR использует bounded `ThreadPoolExecutor`; persistent OCR model service в приложении отсутствует.
- Optional mapping обращается по HTTP к явно настроенному loopback Ollama endpoint. Программа его не запускает и им не владеет.
- Planned middle-row insertion создаёт отдельный app-owned Excel COM instance только на время одной staged operation и всегда закрывает его; держать скрытый Excel между jobs ради скорости запрещено без отдельного доказательства.
- Поэтому нельзя завершать Ollama, Python/Tesseract по имени процесса или любой shared/external service. Idle shutdown применим только к worker/model instance, который будущий код сам запустил и чей exact handle хранит.

## Gate P0 — reproducible baseline

1. Взять единый immutable accepted SHA только после functional Wave 5 и final functional reviewer, зафиксировать source/fixture hashes и Windows runtime version.
2. Добавить отдельной tester-card `scripts/windows_performance_probe.py` и `tests/test_performance_probe.py`; harness не меняет production flow и выдаёт machine-readable stage metrics.
3. На disposable synthetic/approved copies измерить минимум шесть сценариев: cold import, warm repeat, byte-exact no-op, existing-row mismatch, blank-row fill, native middle insertion/new-group action.
4. Сначала провести noise pilot; по нему до сравнения candidate заморозить число повторов и пороги. Затем зафиксировать median/p95: wall and CPU time, peak working set, process/thread count, subprocess calls, disk read/write bytes, cache size и per-stage timings.
5. Параллельно сохранить functional oracle: route/outcome/report projection, mutation manifest, changed cells, target/backup/source hashes, formulas/styles/hyperlinks/x14/CF и action history.
6. Разделить first-run costs (runtime DB bootstrap/cache fill) и steady-state. Не сравнивать cold baseline с warm candidate.

## Профилирование и выбор работ

Read-only debugger/explorer строит ranked bottleneck table с долей времени/памяти и доказательством повторной работы. Benchmark work ID завершается этим evidence и решением `skip` либо `optimize`; production hot paths он не меняет. Broad «ускорить всё» card запрещена.

Кандидаты рассматриваются только при доказанном bottleneck:

- один workbook snapshot/index на проход: group boundaries, canonical RNS и C index вместо повторных load/scan;
- content-hash OCR cache с ключом tool/parser version + DPI/settings, atomic successful entries, bounded LRU size и corruption-as-miss;
- measured Windows-aware OCR concurrency, чтобы не раздувать RAM/CPU и не замедлять диск;
- SQLite indexes, prepared reads и короткие batched transactions для registry snapshot;
- adaptive admin polling/backoff при idle с немедленным wake-up на active job/action;
- lazy initialization тяжёлых app-owned компонентов.

Нельзя кешировать результат через изменение business rules, пропускать target/registry hash recheck, ослаблять OOXML validator или заменять exact comparison приблизительным.

## App-owned idle lifecycle

Если profiling докажет пользу собственного persistent worker/model, его контракт обязателен:

1. Lazy start при первом запросе; owner хранит exact process handle/instance ID и creation metadata.
2. Reference count включает active jobs, queue, pending publication/action и in-flight request.
3. Idle timer запускается только при нуле всех counters; timeout выбирается по Windows baseline и фиксируется в card/tests, а не угадывается заранее.
4. Сначала graceful close, затем bounded terminate только того же handle. Shared endpoint и процессы по имени не затрагиваются.
5. Следующий job прозрачно перезапускает worker; crash/stop не теряет job state и не оставляет publication lock.
6. App exit/restart, sleep/resume и concurrent arrival входят в Windows lifecycle tests.

Для текущего external Ollama этот блок означает `no action`: приложение не имеет права его останавливать.

## Орда и отдельные work ID

### Work A — `construction-group-performance-benchmark-v1`

Создаётся только после immutable functional SHA отдельным planning commit. `cgp-windows-benchmark-harness`: tester, P3, Terra/medium; exact scope только `scripts/windows_performance_probe.py`, `tests/test_performance_probe.py`. После интеграции выполняются baseline/noise runs и read-only P4 profiler. `max_parallel=2`, `max_spawns=3`, `max_retries=1`.

### Work B — `construction-group-optimization-v1`, только при доказанном bottleneck

После закрытия Work A integration owner создаёт новый planning commit от exact benchmark SHA и только в нём замораживает 1–2 независимые developer cards, exact paths и acceptance thresholds. Обе, если их две, стартуют от одного exact planning base, не пересекаются и не зависят друг от друга. `max_parallel=2`, `max_spawns=6`, `max_retries=1`, merge only `--no-ff`. До этого optimization cards не существуют и не запускаются.

Каждый candidate сначала проходит focused functional tests, затем same-machine A/B probe. Candidate без выигрыша отклоняется и не интегрируется. Зависимая или overlapping вторая оптимизация требует отдельного следующего work ID/planning commit от уже известного accepted SHA; frozen card никогда не получает будущий SHA задним числом.

### Work C — `construction-group-release-qualification-v1`

Всегда создаётся отдельным manifest после `skip` Work A либо ACCEPT Work B, поэтому candidate SHA известен заранее. Independent tester read-only выполняет full tracked suite, portable runtime/installer smoke, exact baseline-vs-candidate oracle и cold/warm/no-op resource matrix. Final reviewer: read-only P6 Sol/high. Если qualification требует source remediation, создаётся отдельный bounded work ID; текущий manifest не мутирует. Release разрешён только после hosted exact-main Windows smoke.

## Acceptance and rollback

- Exact records/outcomes/conflicts/proposals/actions совпадают с functional SHA; timing fields исключаются из semantic diff.
- No-op XLSX byte/hash/mtime/backup count unchanged; mutation case имеет тот же allowlist и валидный verified backup.
- Targeted metric улучшается сверх замороженного после noise-pilot threshold; допустимые p95 wall-time/peak-memory отклонения других сценариев также численно фиксируются до candidate run.
- Cache disabled/corrupt/full, one-core/low-memory pressure, locked Excel, restart and sleep/resume fail safely and remain functionally exact.
- Optimization cannot swallow an exception, convert it to empty/no-op success, or remove typed user error/technical-log evidence. A fallback is accepted only when it restores the same semantic oracle; otherwise it fails visibly with the original causal chain preserved.
- Idle shutdown не срабатывает при job/queue/publication и не завершает external Ollama/shared process; restart path прозрачен.
- После structural operation exact PID, доказанный early durable nonce/HWND/PID/creation-time lease+ACK, отсутствует; timeout/exception после lease не оставляет zombie Excel и не затрагивает пользовательские instances. До ownership ACK kill запрещён и workbook ещё не открывается. Paired no-insert control является обязательной correctness-cost и не удаляется как «оптимизация» без эквивалентного доказательства.
- Каждая optimization — отдельный merge commit и откатывается merge revert. Cache/runtime artifacts можно игнорировать/пересоздать; operator DB, PDF и XLSX не удаляются.

## Статус

Это связанный обязательный lifecycle, а не разрешение на speculative edits. Benchmark, optional optimization и final qualification — три разных work ID с собственными exact planning commits/SHA.
