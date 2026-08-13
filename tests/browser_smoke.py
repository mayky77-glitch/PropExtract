"""Manual browser QA run through tests; screenshots are written outside the repo."""
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


BASE = "http://127.0.0.1:18765"
SCREENSHOTS = Path("/tmp/propextract-browser-qa")
SCREENSHOTS.mkdir(parents=True, exist_ok=True)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, color_scheme="light")
    errors: list[str] = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.goto(BASE)
    page.wait_for_load_state("networkidle")
    assert page.locator("h1", has_text="Обновите реестр").is_visible()
    heading_box = page.locator("h1").bounding_box()
    shell_box = page.locator("main.shell").bounding_box()
    assert heading_box and shell_box
    assert abs(heading_box["x"] - shell_box["x"]) < 2
    assert heading_box["width"] >= 700
    assert page.get_by_role("button", name="Перенести данные").is_visible()
    assert page.get_by_text("Программа запущена").is_visible()
    assert page.get_by_role("button", name="Остановить PropExtract").is_visible()
    assert page.get_by_role("button", name="Выбрать", exact=True).count() == 2
    assert page.locator(".brand-mark").evaluate("image => image.complete && image.naturalWidth > 0")

    page.route(
        "**/api/picker",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"path":"C:\\\\PDF документы","cancelled":false}',
        ),
    )
    page.get_by_role("button", name="Выбрать", exact=True).first.click()
    expect(page.get_by_label("Папка с PDF")).to_have_value("C:\\PDF документы")
    page.unroute("**/api/picker")
    page.screenshot(path=SCREENSHOTS / "desktop-light.png", full_page=True)

    page.get_by_role("button", name="Тёмная тема").click()
    assert page.locator("html").get_attribute("data-theme") == "dark"
    assert page.get_by_role("button", name="Тёмная тема").get_attribute("aria-pressed") == "true"
    page.screenshot(path=SCREENSHOTS / "desktop-dark.png", full_page=True)

    def mock_job(route):
        if route.request.method == "POST":
            route.fulfill(status=202, content_type="application/json", body='{"id":"matched-records"}')
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "id": "matched-records",
                "status": "done",
                "progress": 100,
                "stage": "Готово",
                "summary": {
                    "pdf_count": 7,
                    "record_count": 4,
                    "changed_rows": 0,
                    "new_rows": 0,
                    "already_present_count": 4,
                    "already_present_files": ["Разрешение ВЛ 110кВ.pdf", "Продление до 28.11.2026.pdf"],
                    "issue_count": 0,
                    "row_numbers": [584, 585, 586, 587],
                    "new_row_numbers": [],
                    "rows_with_issues": [],
                },
                "documents": [
                    {"id": "doc-1", "filename": "Разрешение ВЛ 110кВ.pdf"},
                    {"id": "doc-2", "filename": "Продление до 28.11.2026.pdf"},
                ],
                "row_cards": [
                    {"row": 584, "number": "38-1-1-2026", "object": "Линейный объект", "outcome": "already_present", "filename": "Разрешение ВЛ 110кВ.pdf", "document_id": "doc-1"},
                    {"row": 585, "number": "38-2-2-2026", "object": "Продление разрешения", "outcome": "already_present", "filename": "Продление до 28.11.2026.pdf", "document_id": "doc-2"},
                ],
                "proposals": [],
            }, ensure_ascii=False),
        )

    page.route("**/api/jobs**", mock_job)
    page.get_by_label("Папка с PDF").fill("C:\\PDF")
    page.get_by_label("Целевой файл Excel").fill("C:\\Реестр.xlsx")
    page.get_by_role("button", name="Перенести данные").click()
    page.get_by_role("heading", name="Данные уже внесены").wait_for(timeout=5000)
    result_text = page.locator("#result").inner_text()
    assert "Разрешение ВЛ 110кВ.pdf" in result_text
    assert "Продление до 28.11.2026.pdf" in result_text
    assert "Уже заполнены" in result_text
    assert "Данные уже есть в таблице" in result_text
    assert "Строка оставлена без изменений." in result_text
    assert page.locator(".sheet-row-marker", has_text="584").count() == 1
    assert page.locator(".record-status--matched", has_text="Совпадает").count() == 2
    assert page.get_by_role("button", name="Открыть PDF").count() == 2
    page.screenshot(path=SCREENSHOTS / "already-present-dark.png", full_page=True)
    page.unroute("**/api/jobs**", mock_job)

    review_state = {"approved": False}

    def mock_review_job(route):
        if route.request.method == "POST" and route.request.url.endswith("/approve"):
            review_state["approved"] = True
            route.fulfill(status=200, content_type="application/json", body='{"status":"approved","backup":"backup.xlsx"}')
            return
        if route.request.method == "POST":
            route.fulfill(status=202, content_type="application/json", body='{"id":"review-records"}')
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "id": "review-records",
                "status": "done",
                "progress": 100,
                "stage": "Готово",
                "summary": {
                    "pdf_count": 2,
                    "record_count": 2,
                    "changed_rows": 0,
                    "new_rows": 0,
                    "already_present_count": 1,
                    "issue_count": 1,
                    "row_numbers": [592, 593],
                    "new_row_numbers": [],
                    "rows_with_issues": [592],
                },
                "documents": [
                    {"id": "doc-review", "filename": "Продление РНС до 31.12.2028.pdf"},
                    {"id": "doc-match", "filename": "Разрешение на этап 2.pdf"},
                ],
                "row_cards": [
                    {"row": 592, "number": "RU-38509306-19-2022", "object": "Строительство жилого дома, этап 1", "outcome": "review_conflict", "filename": "Продление РНС до 31.12.2028.pdf", "document_id": "doc-review"},
                    {"row": 593, "number": "RU-38509306-20-2022", "object": "Строительство жилого дома, этап 2", "outcome": "already_present", "filename": "Разрешение на этап 2.pdf", "document_id": "doc-match"},
                ],
                "proposals": [{
                    "id": "proposal-1",
                    "row": 592,
                    "number": "RU-38509306-19-2022",
                    "field": "Срок действия",
                    "existing": "31.12.2026",
                    "proposed": "31.12.2028",
                    "object": "Строительство жилого дома, этап 1",
                    "filename": "Продление РНС до 31.12.2028.pdf",
                    "document_id": "doc-review",
                    "status": "approved" if review_state["approved"] else "pending",
                }],
            }, ensure_ascii=False),
        )

    page.route("**/api/jobs**", mock_review_job)
    page.get_by_role("button", name="Перенести данные").click()
    page.get_by_role("heading", name="Строки для проверки").wait_for(timeout=5000)
    expect(page.locator(".record-value--existing span")).to_have_text("В таблице")
    expect(page.locator(".record-value--existing strong")).to_have_text("31.12.2026")
    expect(page.locator(".record-value--proposed span")).to_have_text("В документе")
    expect(page.locator(".record-value--proposed strong")).to_have_text("31.12.2028")
    assert page.locator(".sheet-row-marker", has_text="592").count() == 1
    assert page.get_by_role("button", name="Перенести в таблицу").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    page.screenshot(path=SCREENSHOTS / "review-comparison-dark.png", full_page=True)
    page.get_by_role("button", name="Перенести в таблицу").click()
    page.get_by_role("heading", name="Изменения перенесены").wait_for(timeout=5000)
    assert page.get_by_role("button", name="Перенести в таблицу").count() == 0
    assert page.get_by_text("Перенесено", exact=True).count() >= 1
    page.screenshot(path=SCREENSHOTS / "review-approved-dark.png", full_page=True)
    page.unroute("**/api/jobs**", mock_review_job)

    edit_state = {"saved": False, "failed": False, "payloads": []}

    def manual_edit_job():
        proposal_status = "resolved_manual" if edit_state["saved"] else "pending"
        return {
            "id": "manual-records", "status": "done", "progress": 100, "stage": "Готово", "capability": "opaque-capability",
            "summary": {"pdf_count": 1, "record_count": 1, "changed_rows": 1, "new_rows": 0, "already_present_count": 0, "issue_count": 1, "row_numbers": [594], "new_row_numbers": [], "rows_with_issues": [594]},
            "documents": [{"id": "doc-edit", "filename": "РНС для ручной сверки.pdf"}],
            "row_cards": [{"row": 594, "number": "RU-38509306-21-2022", "object": "Объект после ручной проверки" if edit_state["saved"] else "Объект для ручной проверки", "outcome": "review_conflict", "needs_review": True, "filename": "РНС для ручной сверки.pdf", "document_id": "doc-edit", "edit_id": "fresh-edit" if edit_state["saved"] else "edit-1", "editable_fields": [{"key": "object", "label": "Наименование объекта", "type": "text"}, {"key": "end", "label": "Срок действия", "type": "date"}], "editable_values": {"object": "Объект после ручной проверки" if edit_state["saved"] else "Объект для ручной проверки", "end": "31.12.2027"}}],
            "proposals": [{"id": "proposal-edit", "row": 594, "number": "RU-38509306-21-2022", "field": "Наименование объекта", "existing": "Старое имя", "proposed": "Объект для ручной проверки", "object": "Объект для ручной проверки", "filename": "РНС для ручной сверки.pdf", "document_id": "doc-edit", "status": proposal_status, "action": "Исправлено вручную" if edit_state["saved"] else "Перенести изменения"}],
        }

    def mock_manual_edit(route):
        if route.request.method == "POST" and "/edits/" in route.request.url:
            edit_state["payloads"].append(route.request.post_data_json)
            if edit_state["failed"]:
                route.fulfill(status=400, content_type="application/json", body='{"error":"Проверьте введённые данные."}')
            else:
                edit_state["saved"] = True
                route.fulfill(status=200, content_type="application/json", body=json.dumps(manual_edit_job(), ensure_ascii=False))
            return
        if route.request.method == "POST":
            route.fulfill(status=202, content_type="application/json", body='{"id":"manual-records"}')
            return
        route.fulfill(status=200, content_type="application/json", body=json.dumps(manual_edit_job(), ensure_ascii=False))

    page.route("**/api/jobs**", mock_manual_edit)
    page.get_by_role("button", name="Перенести данные").click()
    page.get_by_role("button", name="Исправить данные").click()
    first_edit = page.locator("[data-edit-input]").first
    expect(first_edit).to_be_focused()
    first_edit.fill("Объект после ручной проверки")
    page.get_by_role("button", name="Сохранить исправления").click()
    page.get_by_text("Исправлено вручную", exact=True).first.wait_for(timeout=5000)
    assert edit_state["payloads"] == [{"capability": "opaque-capability", "fields": {"object": "Объект после ручной проверки"}}]
    assert page.get_by_role("button", name="Перенести в таблицу").count() == 0
    assert page.get_by_role("button", name="Исправить данные").count() == 1
    assert page.locator('[data-edit-toggle="fresh-edit"]').count() == 1

    # Server error stays Russian, leaves form usable, and never exposes response internals.
    edit_state.update(saved=False, failed=True, payloads=[])
    page.get_by_role("button", name="Перенести данные").click()
    page.get_by_role("button", name="Исправить данные").click()
    page.locator("[data-edit-input]").first.fill("Ошибка проверки")
    page.get_by_role("button", name="Сохранить исправления").click()
    expect(page.locator("[data-edit-feedback]")).to_have_text("Не удалось сохранить исправления. Проверьте данные и повторите попытку.")
    expect(page.get_by_role("button", name="Сохранить исправления")).to_be_enabled()
    assert "opaque-capability" not in page.locator("#result").inner_text()
    page.unroute("**/api/jobs**", mock_manual_edit)

    def mock_low_quality(route):
        if route.request.method == "POST":
            route.fulfill(status=202, content_type="application/json", body='{"id":"low-quality"}')
            return
        route.fulfill(status=200, content_type="application/json", body=json.dumps({
            "id": "low-quality", "status": "done", "progress": 100, "stage": "Готово", "capability": "opaque-capability",
            "summary": {"pdf_count": 1, "record_count": 1, "changed_rows": 0, "new_rows": 0, "already_present_count": 0, "issue_count": 1, "row_numbers": [595], "new_row_numbers": [], "rows_with_issues": [595]},
            "documents": [{"id": "doc-low", "filename": "Низкое качество OCR.pdf"}], "row_cards": [],
            "proposals": [{"row": 595, "number": "RU-38509306-22-2022", "field": "Разработчик ПД", "existing": "ООО Старое", "proposed": "ООО OCR", "object": "Строка с низким качеством", "filename": "Низкое качество OCR.pdf", "document_id": "doc-low", "quality": "review", "review_details": "Низкая уверенность OCR: проверьте PDF вручную."}],
        }, ensure_ascii=False))

    page.route("**/api/jobs**", mock_low_quality)
    page.get_by_role("button", name="Перенести данные").click()
    page.get_by_role("heading", name="Строки для проверки").wait_for(timeout=5000)
    assert page.get_by_text("Низкая уверенность OCR: проверьте PDF вручную.").is_visible()
    assert page.get_by_role("button", name="Перенести в таблицу").count() == 0
    page.unroute("**/api/jobs**", mock_low_quality)

    page.get_by_label("Папка с PDF").fill('"/path/that/does/not/exist"')
    page.get_by_label("Целевой файл Excel").fill("/path/that/does/not/exist.xlsx")
    page.get_by_role("button", name="Перенести данные").click()
    page.get_by_role("heading", name="Реестр не изменён").wait_for(timeout=5000)
    error_text = page.locator("#result-paths").inner_text()
    assert "Проверьте подключение к PropExtract и параметры запуска." in error_text
    assert "/path/that/does/not/exist" not in error_text
    assert page.get_by_role("button", name="Перенести данные").is_enabled()

    page.goto(f"{BASE}/help")
    page.wait_for_load_state("networkidle")
    assert page.locator("h1", has_text="От папки со сканами").is_visible()
    page.screenshot(path=SCREENSHOTS / "help-dark.png", full_page=True)

    mobile_context = browser.new_context(viewport={"width": 390, "height": 844}, color_scheme="light")
    mobile = mobile_context.new_page()
    mobile.goto(BASE)
    mobile.wait_for_load_state("networkidle")
    assert mobile.get_by_role("button", name="Перенести данные").is_visible()
    assert mobile.get_by_role("button", name="Остановить PropExtract").is_visible()
    edit_state.update(saved=False, failed=False, payloads=[])
    mobile.route("**/api/jobs**", mock_manual_edit)
    mobile.get_by_label("Папка с PDF").fill("C:\\PDF")
    mobile.get_by_label("Целевой файл Excel").fill("C:\\Реестр.xlsx")
    mobile.get_by_role("button", name="Перенести данные").click()
    mobile.get_by_role("button", name="Исправить данные").click()
    expect(mobile.locator("[data-edit-input]").first).to_be_focused()
    assert mobile.locator("[data-row-edit-form]").is_visible()
    assert mobile.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    mobile.screenshot(path=SCREENSHOTS / "mobile-light.png", full_page=True)
    mobile_context.close()

    page.goto(BASE)
    page.wait_for_load_state("networkidle")
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Остановить PropExtract").click()
    page.get_by_role("heading", name="PropExtract остановлен").wait_for(timeout=5000)
    page.screenshot(path=SCREENSHOTS / "shutdown.png", full_page=True)
    unexpected_errors = [message for message in errors if "400 (Bad Request)" not in message]
    assert unexpected_errors == [], unexpected_errors
    browser.close()

print(f"Browser QA passed; screenshots: {SCREENSHOTS}")
