"""Manual browser QA run through tests; screenshots are written outside the repo."""
from pathlib import Path

from playwright.sync_api import sync_playwright


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
    assert page.get_by_role("button", name="Выбрать", exact=True).count() == 2
    assert page.locator(".brand-mark").evaluate("image => image.complete && image.naturalWidth > 0")
    page.screenshot(path=SCREENSHOTS / "desktop-light.png", full_page=True)

    page.get_by_role("button", name="Тёмная тема").click()
    assert page.locator("html").get_attribute("data-theme") == "dark"
    assert page.get_by_role("button", name="Тёмная тема").get_attribute("aria-pressed") == "true"
    page.screenshot(path=SCREENSHOTS / "desktop-dark.png", full_page=True)

    page.get_by_label("Папка с PDF").fill("/path/that/does/not/exist")
    page.get_by_label("Целевой файл Excel").fill("/path/that/does/not/exist.xlsx")
    page.get_by_role("button", name="Перенести данные").click()
    page.get_by_role("heading", name="Реестр не изменён").wait_for(timeout=5000)
    assert page.get_by_role("button", name="Перенести данные").is_enabled()

    page.goto(f"{BASE}/help")
    page.wait_for_load_state("networkidle")
    assert page.locator("h1", has_text="От папки со сканами").is_visible()
    page.screenshot(path=SCREENSHOTS / "help-dark.png", full_page=True)

    mobile = browser.new_page(viewport={"width": 390, "height": 844}, color_scheme="light")
    mobile.goto(BASE)
    mobile.wait_for_load_state("networkidle")
    assert mobile.get_by_role("button", name="Перенести данные").is_visible()
    mobile.screenshot(path=SCREENSHOTS / "mobile-light.png", full_page=True)
    assert errors == [], errors
    browser.close()

print(f"Browser QA passed; screenshots: {SCREENSHOTS}")
