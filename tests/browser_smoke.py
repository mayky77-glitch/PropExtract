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
    assert "Строка Excel 584" in result_text
    assert "Строка не изменена: данные уже есть в таблице." in result_text
    assert page.get_by_role("button", name="Открыть PDF").count() == 2
    page.screenshot(path=SCREENSHOTS / "already-present-dark.png", full_page=True)
    page.unroute("**/api/jobs**", mock_job)

    page.get_by_label("Папка с PDF").fill('"/path/that/does/not/exist"')
    page.get_by_label("Целевой файл Excel").fill("/path/that/does/not/exist.xlsx")
    page.get_by_role("button", name="Перенести данные").click()
    page.get_by_role("heading", name="Реестр не изменён").wait_for(timeout=5000)
    error_text = page.locator("#result-paths").inner_text()
    assert "Проверьте папку с PDF, файл Excel и параметры операции." in error_text
    assert "/path/that/does/not/exist" not in error_text
    assert page.get_by_role("button", name="Перенести данные").is_enabled()

    page.goto(f"{BASE}/help")
    page.wait_for_load_state("networkidle")
    assert page.locator("h1", has_text="От папки со сканами").is_visible()
    page.screenshot(path=SCREENSHOTS / "help-dark.png", full_page=True)

    mobile = browser.new_page(viewport={"width": 390, "height": 844}, color_scheme="light")
    mobile.goto(BASE)
    mobile.wait_for_load_state("networkidle")
    assert mobile.get_by_role("button", name="Перенести данные").is_visible()
    assert mobile.get_by_role("button", name="Остановить PropExtract").is_visible()
    mobile.screenshot(path=SCREENSHOTS / "mobile-light.png", full_page=True)

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
