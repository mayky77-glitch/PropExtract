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
  - domain/rns
  - knowledge/windows
links:
  - "[[../ORCHESTRATION|Orchestration]]"
  - "[[map-object-group-current-flow]]"
  - "[[orda-construction-group-routing-waves]]"
  - "[[orda-middle-row-insertion-plan]]"
  - "[[orda-failure-fallback-contract]]"
  - "[[orda-performance-optimization-plan]]"
  - "[[../components/workbook-publication]]"
---

# План Орды: маршрутизация РНС по стройке

## Цель v1

Добавить поставляемый с программой справочник `официальное наименование стройки ↔ код стройки`, находить по нему блок Excel, внутри блока выбирать существующую строку по canonical РНС, а наименование объекта проверять существующим механизмом расхождений. Если РНС отсутствует, строка создаётся только после ввода оператором четырёхзначного номера объекта. Админка также должна безопасно создавать новую стройку одновременно в локальном реестре и выбранном XLSX.

Windows — release target. После функциональной интеграции обязательна measurement-first оптимизация скорости/ресурсов без изменения результатов; Linux сохраняет общую Python-совместимость, но отдельно пока не оптимизируется.

## Не входит в v1

- fuzzy/LLM-сопоставление названий и автоматическая запись по догадке;
- автоматическая генерация следующего `.xxxx`;
- физическое перемещение уже найденной строки между группами;
- hard delete справочника, сетевой DB-сервер и multi-user sync;
- самописный raw-OOXML fallback для middle insertion без установленного Microsoft Excel;
- изменение security без доказанного функционального бага;
- остановка внешнего/shared Ollama или любого процесса, которым программа не владеет.

## Проверенные исходные факты

- Сейчас PDF-записи группируются по canonical РНС, Excel ищется глобально по F, а новая строка добавляется после последней заполненной строки листа.
- Столбец C сейчас не моделируется программой.
- В реальном реестре есть отдельные заголовки групп в D и общий кодовый префикс у дочерних строк.
- Все 508 однозначных кодов с суффиксом имеют четыре цифры; встречаются legacy-значения без суффикса, `-`, несколько кодов в одной ячейке и повторяющиеся полные C. Поэтому C не является уникальным row ID.
- В реестре есть одинаковые РНС в разных группах. Группа должна ограничивать поиск, а не глобальная уникальность РНС.
- Целевая legacy-группа имеет подготовленный формульный хвост Y:Z. Его строки можно использовать по одной только после доказательства принадлежности этой группе; это не настраиваемый резерв и не любой blank C.
- Текущий лист имеет business-data до 605 и preformatted/formula tail до 1001; filter/defined range заканчивается на 605. Текущая группа может заполнять 606 далее без shift; новая стройка может начать header с первой свободной business row. Позднее расширение старой группы требует native insertion перед следующим header.
- В книге 1 996 формул Y:Z и 616 dashboard formulas, 615 из них ссылаются на реестр; x14/DV ranges фрагментированы. Поэтому безопасный middle insert выполняет установленный Windows Excel COM, не `openpyxl.insert_rows()`.
- Tesseract/Poppler уже завершаются после каждого bounded subprocess. Ollama вызывается как внешний loopback endpoint и не запускается приложением, поэтому текущему коду нечего безопасно «гасить» как собственную модель.

## Обязательный business-flow

1. Из PDF сохраняется исходный `raw_object`.
2. В начале `raw_object` ищется ровно одно официальное название из справочника: нормализованное точное начало плюс граница пунктуации/пробела; при вложенных названиях выигрывает самое длинное.
3. Из остатка формируется `object_tail`, например `Этап 13.5. ...`. Исходный текст сохраняется для контекста; в D предлагается/записывается именно хвост.
4. В выбранном Excel ищется ровно один header: D равно official name, A/B/C/E/F пусты. Группа идёт до следующего валидного header; repeated header той же стройки считается конфликтом, а не continuation.
5. Структурированные C внутри группы должны относиться к коду справочника. Blank/legacy `-` допускаются; чужой распознаваемый префикс делает block конфликтным.
6. Внутри блока ищется canonical РНС:
   - одна строка — существующая запись;
   - несколько — review, без записи;
   - ни одной — выполняется глобальная защитная проверка.
7. Если внутри блока строка найдена, из D также удаляется только точный официальный префикс этой же стройки, когда он действительно присутствует; сравниваются два хвоста через существующий `field_comparison_equal`. Raw D и raw PDF остаются для контекста. Совпадение — no-op; отличие — существующая карточка расхождения/approval с предлагаемым значением `object_tail`. Строка не перемещается.
8. Если внутри блока РНС нет, но он есть вне блока, новая строка автоматически не создаётся: `rns_wrong_block`, оператор видит конфликт.
9. Только полное отсутствие РНС создаёт `pending_object_number`. Excel на этом этапе не меняется.
10. Оператор вводит только четыре цифры после точки. Сервер сохраняет leading zero и строит полный C: `code_prefix + "." + suffix`.
11. Под общим publication lock сервер повторно проверяет hash, registry revision, group boundaries, РНС и code/name consistency. Он заполняет доказанную blank row либо на staged copy нативно вставляет одну row перед следующим header, затем validate → backup → second hash → atomic replace.

## Создание новой группы из админки

Обязательные поля: официальное название, code prefix и выбранный XLSX. Worksheet и versioned group-template определяются workbook contract; separator `.` и four-digit suffix не вводятся вручную.

1. Сервер валидирует форму, уникальность name/code и workbook/sheet contract.
2. В runtime DB создаются `draft` construction и journal-операция; draft не участвует в routing и не может стать active через обычный PATCH.
3. Новый header ставится в первую validated blank business row после последней заполненной строки (для текущего workbook — 606), под ним создаётся ровно одна bootstrap row. Existing Y/Z/x14 template должен остаться валиден; при одновременном объекте bootstrap сразу заполняется.
4. Под единым publication lock повторно проверяются Excel hash и DB generation; создаётся verified backup, XLSX атомарно заменяется, затем запись реестра становится active.
5. Generic journal durable хранит intent, stable target identity, pre/control/staged/post hashes, generation, manifest, template и finalization flags до внешних side effects. Recovery: post-hash → только idempotent finalize DB/binding/report; pre-hash → fresh workbook/registry revalidation перед новым stage, без blind replay; любой третий hash → manual repair без overwrite/activation. Активной записи из provision без пригодного Excel-блока быть не должно.
6. После заполнения bootstrap постоянный запас не создаётся. Если следующая row уже является другим header, отдельный app-owned Excel COM instance вставляет одну row прямо перед ним и сразу заполняет; нижние группы физически сдвигаются на `+1`, повторный header не создаётся.

## Контракт совпадений и конфликтов

| Ситуация | Результат |
| --- | --- |
| Название стройки не найдено | `route_unknown`, подсказка добавить стройку в справочник, Excel unchanged |
| Реестр знает стройку, но block отсутствует | `block_missing`, предложение provision group; импорт не создаёт строку |
| Стройка archived, существующий РНС найден | существующую строку можно сверить; новая строка запрещена до reactivate |
| Header стройки отсутствует/повторяется | `block_missing` / `block_duplicate`, Excel unchanged |
| Один РНС найден внутри нужной группы | использовать строку, затем сравнить D |
| Один РНС внутри и такой же РНС в другой группе | выбранная группа разрешает неоднозначность; использовать внутреннюю строку |
| РНС нет внутри, но есть снаружи | `rns_wrong_block`, не создавать дубль |
| Несколько РНС внутри | `rns_block_conflict`, Excel unchanged |
| РНС нигде нет | запросить номер объекта |
| Суффикс не `^[0-9]{4}$` | inline error, Excel unchanged |
| Полный C уже есть и D эквивалентно | повтор C допустим: это не row identity |
| Полный C уже есть с другим D | `object_code_name_conflict`, новая строка не создаётся |
| Нужна middle insertion, но desktop Excel недоступен | `excel_required_for_middle_insert`, Excel unchanged |
| Native insertion/semantic formula validation не прошла | `structural_insert_failed`, Excel unchanged |
| Попытка rename/recode bound entry | `binding_alignment_required`; DB/XLSX unchanged |
| Excel/registry изменились после анализа | `stale`, перезапустить проверку |

## Контракт ошибок и fallback

Обязателен [[orda-failure-fallback-contract]]: fallback либо проходит полный исходный oracle как `recovered`, либо даёт понятную русскую typed error/next step и correlated local log. Silent success/no-op/empty result запрещён; post-hash failure только идемпотентно финализируется.

## Справочник Windows v1

В Git и source archive хранится versioned seed: `rns_import_server/data/construction_registry.seed.sqlite3` плюс manifest с schema/seed revision/digest. Это read-only источник поставки, который валидируется при сборке и старте. Writable runtime DB: `%LOCALAPPDATA%\PropExtract\construction-registry\registry.sqlite3`; он переживает reinstall/update и не требует UAC.

Первый запуск атомарно разворачивает runtime DB из seed. Каждая seed entry имеет стабильный `seed_entry_id`; runtime хранит origin, last-applied seed revision и last-applied base values в отдельном seed-state. Three-way merge обновляет untouched unbound entry, сохраняет local-only entry, а разные local/seed edits создают conflict без overwrite. У bound entry status-only seed update допустим, но изменение official name/code создаёт `binding_alignment_conflict` и не меняет active route/XLSX. Seed removal только архивирует untouched entry; локально изменённая даёт conflict. Вся reconciliation transactionally rollback-ится при crash.

Чтобы approved локальную запись получили все будущие копии, отдельная deterministic maintenance-команда экспортирует/валидирует новый seed+manifest, после чего человек commit/push-ит их в Git. Запущенная программа сама Git не изменяет.

Минимальная схема:

- `registry_meta`: schema version, seed revision, monotonically increasing `generation`, timestamps;
- `constructions`: internal ID, stable optional `seed_entry_id`, origin, `code_prefix`, `official_name`, normalized name, `status=draft|active|archived`, row revision, timestamps;
- `registry_seed_state`: stable seed ID, last-applied revision and base code/name/status/digest;
- `construction_bindings`: construction ID, stable workbook-contract/target identity, sheet, template version and verified state; row/header coordinates не хранятся, block заново находится semantic name/code scan при каждом open/restart;
- `workbook_operation_journal`: durable API for `group_provision|new_row` with mutation mode `bootstrap_fill|blank_fill|middle_insert`; operation/idempotency/consumer ID, construction + canonical RNS, stable target/sheet/template identity, expected generation, intent/manifest version+digest, pair nonce, pre/staged/control/post/backup hashes, validation digest, operation directory, Excel lease/build metadata, phase, failure code and separate capability/binding/history/report finalization flags;
- unique normalized official name and code prefix;
- fixed v1 grammar: prefix `^[0-9]{3}-[0-9]{7}$`, separator `.`, suffix exactly four digits.

SQLite используется из standard library portable Python. Нужны short transactions, busy timeout, integrity check on open и verified backup только перед schema migration. Journal state меняется CAS-операциями; exact candidate/post-hash и manifest durable commit-ятся с `synchronous=FULL` до `os.replace`. Unique operation ID служит idempotency key для binding/history/report/capability. Отдельный audit/security subsystem, DB UI backup manager и network sync не нужны.

Admin API v1:

- `GET /api/constructions` — список + generation;
- `POST /api/constructions/provision` — единственный admin-create: создать draft и новый Excel-блок по обязательным полям, затем active с journal/recovery;
- `PATCH /api/constructions/{id}` — до provision исправить draft; у bound active/archived менять только status с `expected_generation`; reactivation повторно валидирует binding;
- hard delete отсутствует;
- `POST /api/jobs/{job_id}/new-rows/{pending_id}` — передать job capability и suffix.

Bound official name/code через обычный PATCH неизменяемы, потому что они связаны с header D и child C. Rename/recode требует отдельной будущей journalled XLSX migration; v1 возвращает `binding_alignment_required`. PATCH не создаёт и не активирует draft. Legacy/seed active entry без блока может дать `block_missing`, но новое admin-create не может обойти provision contract.

## UI v1

### Страница «Стройки»

- таблица code/name/status;
- форма создания группы: official name, code prefix, target XLSX, preview и явное подтверждение;
- correction draft до provision; для bound entry только archive/reactivate, без rename/recode/delete;
- ошибки duplicate/invalid/stale на русском;
- provisioning progress/recovery и понятные `block_missing`, `excel_required_for_middle_insert`, `structural_insert_failed`, `stale`;
- изменения применяются к следующему запуску; во время активной публикации mutation отклоняется либо ждёт окончания общего gate.

Начальный официальный список должен быть подтверждён владельцем и очищен от частных объектных данных: в Git попадают только официальные construction name/code и технический manifest, не содержимое рабочего XLSX.

### Карточка новой строки

- показывает стройку, фиксированный code prefix, РНС, `object_tail` и исходный PDF;
- input `type=text`, `inputmode=numeric`, maxlength 4, чтобы не потерять leading zero;
- live preview полного C;
- до нажатия «Создать строку» явно сообщает, что Excel не изменён;
- invalid/stale/structural-insert errors остаются в карточке; success показывает строку и полный C, capability становится one-shot consumed;
- другие безопасные существующие строки могут публиковаться независимо; pending новая строка остаётся post-job action.

## Безопасная запись XLSX

### Разрешено в v1

- сначала использовать только доказанную blank/preformatted row внутри нужного блока; произвольный blank C слотом не считается;
- если её нет, на staged-копии установленный Microsoft Excel выполняет native `Rows(k).Insert` перед следующим header. Созданная row сразу заполняется; continuation header и пустой запас запрещены;
- A остаётся последовательным видимым номером: data rows от insertion point детерминированно перенумеровываются, headers остаются blank. Identity — construction + canonical RNS, не row/A;
- C — полный code, D — `object_tail`, F и остальные поля идут через current mapping; W получает один новый hyperlink;
- Excel переносит нижние groups, formulas, dashboard references, CF/x14, DV, merges, filter и defined names. Из того же pre-hash проходит native no-insert control на той же Excel build/settings; validator сначала отделяет Excel-wide recalculation/normalization, затем проверяет candidate mapping control `r<k→r`, `r>=k→r+1`, new row `k`;
- moved Y/Z сохраняют equivalent R1C1 pattern; новая row получает template formulas. Formula count растёт ровно на ожидаемый набор, dashboard ranges включают новую row, full native recalculation не даёт новых errors;
- staging, early durable nonce/HWND/PID/creation-time lease with ACK, paired control, generic operation journal, verified backup, second target hash и atomic replace следуют [[orda-middle-row-insertion-plan]].

### Запрещено в v1

Прямой `openpyxl.insert_rows()`, continuation/repeated header, запись строки под чужой группой и raw-OOXML fallback запрещены. Если COM/preflight/formula/x14 validation не проходят, target остаётся byte-identical.

## Gate 0 Орды

План пока не является launchable card set. Перед реализацией integration owner обязан:

1. Получить явную команду владельца начать implementation. После запуска accepted code и validated seed+manifest должны быть commit/push в Git как уже утверждённая часть scope; текущий planning-only turn ничего не публикует.
2. Разрешить dirty overlap: user README сохранить; текущий принятый UI closeout либо опубликовать отдельным commit, либо явно исключить. Новая работа не стартует из dirty root.
3. Выбрать clean exact SHA. После этого создать planning commit с master specification, Gate manifest и frozen cards; этот commit становится `published_base_sha`, `wave_base_sha`, `shared_contract_sha`.
4. Записать exact baseline: status, full pytest, compileall, Node syntax, portable Windows self-test, browser diagnostic и diff check.
5. Заморозить synthetic fixtures без частных данных: соседние groups, insertion before headers 6/10/104, duplicate RNS, blank row 606, formulas Y:Z + dashboard references, hyperlinks, merges, filter/defined names, DV, x14 и unsupported-feature cases.
6. Заморозить failure/fallback matrix: все injected exception/timeout/retry-exhaustion branches имеют typed public outcome, важную technical запись и либо verified recovery, либо fail-closed state без ложного success.
7. Подтвердить sanitized initial official seed и versioned sanitized group-template; решения four-digit suffix, Git-tracked seed, `%LOCALAPPDATA%`, admin group creation и Windows-first уже зафиксированы владельцем.
8. Инициализировать Orda state вне repository. Параметры: `max_parallel=3`, десять write cards, `max_spawns=16`, `max_retries=1`, merge only `--no-ff`.
8. Зарезервировать все scopes текущей волны. Placeholder, overlap, dirty dependency или SHA mismatch закрывают Gate 0.

## Исполнение и приёмка

Точные dependency waves, scopes, модели, acceptance matrix, integration order и rollback вынесены в [[orda-construction-group-routing-waves]]. После immutable functional SHA запускается lifecycle [[orda-performance-optimization-plan]]: отдельные benchmark, optional optimization и final qualification work ID. Отсутствие доказанного выигрыша означает нулевой optimization diff, а не рискованный тюнинг.

## Stop conditions requiring owner decision

- иной suffix/separator/multi-code, automatic fuzzy matching или destructive registry reset/import-replace;
- shared/network registry DB, несколько Windows users либо rename/recode bound группы без staged XLSX migration;
- middle insertion без desktop Excel/raw-OOXML fallback либо остановка external Ollama/shared process;
- момент запуска implementation и release promotion.
