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
  - domain/xlsx
  - knowledge/windows
links:
  - "[[orda-construction-group-routing-plan]]"
  - "[[orda-construction-group-routing-waves]]"
  - "[[../components/workbook-publication]]"
---

# Windows-план: физическая вставка строки внутрь группы

## Owner decision

Новый объект должен физически находиться внутри единственного исходного блока стройки. Continuation/repeated header запрещён. Если подготовленной пустой строки в блоке нет, программа вставляет одну строку непосредственно перед следующим group header; все нижние строки сдвигаются на `+1`.

## Почему нужен Microsoft Excel

`openpyxl.insert_rows()` сдвигает cell coordinates, но не исправляет полностью formula references, merges, data/conditional validation, autoFilter, defined names, tables и x14 `extLst`. Прямой raw-OOXML transformer для этого реестра должен также корректно переписать 615 cross-sheet dashboard formulas и сотни x14 `sqref`, что слишком рискованно для v1.

Windows v1 использует установленный desktop Microsoft Excel через отдельный COM instance на staged-копии. Excel выполняет native row insertion и пересчёт; PropExtract остаётся authority: определяет точку, заполняет только allowlisted cells, проверяет semantic diff, backup/hash и публикует атомарно.

Без Excel все прежние import/check/edit/no-op функции продолжают работать. Только операция физической вставки возвращает `excel_required_for_middle_insert` и не меняет XLSX.

## Проверенный target contract

- `Реестр РНС`: `A1:AQ1001`, 1 996 формул Y:Z;
- `Дашборд`: 616 формул, 615 ссылаются на `Реестр РНС`, включая ranges до 1001;
- autoFilter и `_FilterDatabase`: `A3:AQ605`;
- data validation: `S104:S159`, `R104:R154` плюс x14 extensions;
- крупный фрагментированный x14 CF/DV `extLst`, 209 hyperlinks, 12 merges;
- no tables/drawings/comments/external links/calcChain; calc properties требуют full calculation;
- текущая последняя группа уже имеет подходящие blank/preformatted rows 606–1001: их можно заполнять без physical shift после отдельной validation.

## Structural preflight

Под общим publication lock сервер заново сканирует workbook, а не доверяет row из DB/job:

1. Проверяет target SHA, registry generation, sheet, exact group header/name/code и canonical RNS absence.
2. Находит следующий group header и вычисляет `insertion_row`.
3. Если внутри группы есть доказанная empty template row, выбирает её без insertion.
4. Иначе проверяет, что insertion не разрезает vertical merge/array/data-table/spill formula и workbook не encrypted/protected/read-only.
5. V1 fail-closed при новых неаттестованных tables, drawings, controls, pivots/slicers, threaded comments, external links или Excel repair state.

## Native insertion algorithm

1. Сначала создать и durable commit-нуть generic `workbook_operation_journal`: operation/consumer ID, random owner nonce, operation directory, kind/mutation mode, construction + canonical RNS, stable target identity, pre-hash, expected registry generation, group/next-header fingerprints и intended insertion row.
2. Из одного verified pre-hash создать две staged-копии в одном operation directory и связать random `pair_nonce`: `control` без insertion и `candidate` для insertion. Обе обрабатываются одним adapter, одной Excel build/settings и с ровно одной открытой workbook за раз.
3. Parent до старта adapter снимает snapshot Excel PID. Adapter создаёт hidden `Excel.Application`, немедленно получает `Application.hWnd` и через `GetWindowThreadProcessId` — exact Excel PID, затем **до `Workbooks.Open`** атомарно пишет и flush-ит `excel-lease.json`: operation ID, owner nonce, adapter PID/start time, Excel PID/HWND/start time и Excel build.
4. Parent проверяет nonce, image=`EXCEL.EXE`, PID creation time и HWND→PID, durable commit-ит lease в journal и атомарно выдаёт `lease-ack.json`. Adapter запрещено открывать workbook до nonce-matched ACK. Без ACK он вызывает `Quit()` через ещё принадлежащий ему COM reference и выходит.
5. Передать request/result через JSON files, не command-line cell data. Установить `DisplayAlerts=False`, `EnableEvents=False`, `AskToUpdateLinks=False`, `UpdateLinks=0`; открывать только ожидаемую staged copy writable.
6. Сначала открыть `control`, выполнить `CalculateFullRebuild`, сохранить и закрыть без cell/row mutations. Затем открыть `candidate` и выполнить `Rows(k).Insert(xlShiftDown, xlFormatFromLeftOrAbove)`. Старый next header становится `k+1`, новая row `k` остаётся в исходной группе.
7. Из последней validated data-row той же группы перенести row height, cell formats и validation contract без старых values/hyperlink. Y/Z задать через template `FormulaR1C1`: relative refs указывают на новую row, absolute/named refs не меняются.
8. Записать только allowlisted A:X/AA fields. A — видимый ordinal: детерминированно перенумеровать data rows от insertion point вниз, пропуская group headers; identity остаётся construction + canonical RNS. W получает один новый hyperlink; old targets не меняются.
9. Убедиться, что autoFilter/defined range включают новую populated row, а Excel сдвинул DV, merges, CF/x14 и dependent dashboard ranges. Выполнить тот же `CalculateFullRebuild`, проверить отсутствие Excel errors, сохранить и закрыть `candidate`.
10. В `finally` освободить COM proxies, вызвать `Quit()` только созданного instance и дождаться исчезновения leased PID. При timeout parent повторно проверяет operation ID/nonce + HWND→PID + creation time + image и завершает только этот still-matching PID. PID из простого snapshot никогда не является достаточным разрешением на kill; user Excel не трогается.
11. Python открывает `control` и `candidate` read-only (`data_only=False` и cached-value passes) и выполняет raw-OOXML semantic validation. Он никогда не сохраняет их через OpenPyXL.
12. Записать pair nonce, control hash/semantic digest, candidate post-hash, Excel build/settings и exact mutation manifest в journal; fsync staged candidate и durable transition `validated`. Затем создать verified backup, durable записать его hash/`backup_verified`, повторно проверить target hash/lock и выполнить same-volume `os.replace`.
13. После replace идемпотентно зафиксировать `published`, consume capability и finalize binding/history/report по operation ID; затем `finalized`. Control никогда не публикуется и удаляется только после завершения audit/recovery.

## Formula and structure oracle

Для insertion at `k` validator сначала сравнивает original → paired native `control`: literal business values, formula text/R1C1, styles, hyperlinks и structure должны остаться semantically equal. Разрешаются только доказанные Excel package normalization, calc metadata и recalculated cached-formula values. Затем `candidate` сравнивается с этим же control по mapping: control `r < k → r`, `r >= k → r+1`, inserted row → `k`.

- Все old logical rows сохраняют values, styles, number formats и hyperlink targets по mapping; исключение — ожидаемая последовательная перенумерация A.
- Старая Y/Z formula в moved row сохраняет тот же R1C1 pattern и ссылается на собственную новую row.
- Формулы новой row ровно соответствуют template Y/Z; formula count увеличивается на два для текущего contract.
- Cross-sheet formulas, whose range contains `k`, включают новую row; known dashboard totals после full rebuild согласуются с independent record oracle.
- Множество mapped formula errors равно control; новая row error-free. Нет новых `#REF!`, `#VALUE!`, `#NAME?`, `#DIV/0!`, `#N/A`. Stale/volatile cached results не сравниваются с original: insertion-specific differences ищутся относительно paired control, а deterministic dashboard totals сверяются с independent post-data oracle.
- CF/x14/DV rule fingerprints, priorities, formulas and dxf остаются теми же; разрешены только ожидаемые transformed `sqref` и coverage новой row.
- autoFilter и `_FilterDatabase` совпадают; merges below `k` shifted `+1`; dimension/row count увеличены ровно на одну.
- No-op и заполнение существующей blank row не сдвигают старые coordinates/formulas.

Любой mismatch отменяет publication; target остаётся byte-identical.

## Concurrency, history and recovery

- Structural insert, import, proposal approval, manual edit and group provision share one workbook publication lock.
- Pending actions never authorize a physical row. Under lock they re-resolve construction + canonical RNS; changed hash/header makes them stale/replanned.
- Historical `row` remains “coordinate at event time”; new history also stores construction ID, canonical RNS, workbook pre/post hash and operation ID. Old history is not rewritten.
- Generic journal phases: `planned → staged → excel_launching → excel_owned → control_saved → candidate_saved → validated → backup_verified → published → finalized`; non-COM blank fill пропускает native phases. Отдельные flags отмечают capability, binding, history и report. Каждый side effect идемпотентен по unique operation ID.
- Recovery под publication lock: target `pre_hash` до publication → не replay stale row, а fresh semantic re-resolution и re-authorization; provision остаётся resumable non-routable draft. Target `post_hash` → только record/finalize незавершённые flags, никогда не вставлять повторно. Target `pre_hash` при journal phase≥published или любой third hash → `manual_repair` без overwrite/activation.
- Crash после control, но до validated candidate, инвалидирует пару: control/candidate создаются заново из того же ещё актуального pre-hash с новым pair nonce. Смешивать outputs разных lease/build/attempt запрещено.
- Timeout/hang before-open/open/insert/calc/save обрабатывается только по validated durable lease. Если ownership ещё не доказан, kill Excel запрещён; workbook к этому моменту ещё не открыт, операция завершается `cleanup_unverified` и target не меняется.

## No-silent-fallback rule

- COM/open/save/recalc/validation/journal/backup/replace/finalization exceptions сохраняют первоначальный cause, exact stage и HRESULT/WinError; запрещено вернуть empty result, `success` или `no-op`.
- Bounded retry считается recovery только после повторного прохождения того же preflight, formula/structure oracle и post-hash checks. Иначе UI получает typed error + operation ID + следующий шаг, а local technical log — полный causal record.
- No-Excel не переключается на OpenPyXL/raw OOXML. Failed formula oracle не публикует candidate. Cleanup failure не скрывает исходную ошибку и добавляется отдельным causal item.
- Если post-hash уже опубликован, failure history/report не предлагает повторить insertion: UI показывает recoverable finalization state, journal завершает его идемпотентно.
- Primary technical log пишется в LocalAppData data-root, bounded fallback — operation directory/`%TEMP%`. Двойной отказ логирования сам становится visible `technical_log_unavailable`; target state остаётся доказуемым по journal/hash.

## Blocking Windows acceptance

- Fill validated legacy blank row 606 without shift; formulas/dashboard intact, filter extended.
- Insert before every observed next header (6, 10, 104) and confirm new row remains in previous group.
- Insert inside filter, DV and x14 ranges; old rows map exactly by `+1`.
- Y/Z and all dashboard formulas pass native full recalculation with expected totals and no new errors.
- Paired no-insert control with deliberately stale unrelated cached formulas proves that Excel-wide recalc/normalization is not reported as insertion diff; insertion-specific totals match the independent oracle.
- Old 209 hyperlinks remain exact; exactly one target is added.
- All failures before publication leave source at pre-hash. Crash after `os.replace` permits only exact post-hash and recovery finalizes without a repeated insertion; a third hash is never overwritten.
- Concurrent proposal/manual edit and repeated capability cannot overwrite or double-insert.
- Hang injection before-open/open/insert/calc/save leaves no leased Excel; a pre-opened user Excel and a reused PID are never terminated.
- Crash injection after COM save, durable post-hash, replace and every history/report finalization step yields exactly one physical row and one logical event after restart.
- Fault injection в каждый catch/retry/fallback доказывает один из двух результатов: full-oracle `recovered` либо понятный public error с operation ID и correlated technical record; false success/no-op отсутствует.
- Real Windows Excel 365 x64 opens/saves result without repair/compatibility dialog; hosted no-Office runner verifies safe negative path.

## Explicit limitation

Middle insertion now requires installed desktop Microsoft Excel on Windows. A no-Excel/raw-OOXML implementation is a separate large project and must not be presented as a fallback until it has its own formula/x14 coordinate-transform proof.
