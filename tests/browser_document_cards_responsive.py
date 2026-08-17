"""Browser regression for document-card layout at responsive breakpoints."""
import json
import socket
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(base: str) -> None:
    for _ in range(50):
        try:
            import urllib.request

            with urllib.request.urlopen(f"{base}/health", timeout=0.2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Local test server did not start")


def public_mock_job() -> dict[str, object]:
    return {
        "id": "responsive-document-card",
        "status": "done",
        "progress": 100,
        "stage": "Готово",
        "summary": {
            "pdf_count": 1,
            "record_count": 0,
            "changed_rows": 0,
            "new_rows": 0,
            "already_present_count": 0,
            "issue_count": 0,
            "row_numbers": [],
            "new_row_numbers": [],
            "rows_with_issues": [],
            "out_of_scope_count": 1,
            "unidentified_permit_count": 0,
            "processing_failed_count": 0,
        },
        "documents": [{
            "id": "public-document-1",
            "filename": "public-sample.pdf",
            "outcome": "out_of_scope",
            "error": "Документ не относится к РНС-потоку импорта.",
            "hint": "Проверьте документ вручную и повторите запуск.",
        }],
        "row_cards": [],
        "proposals": [],
    }


def layout(page, width: int) -> dict[str, float | int | str]:
    page.set_viewport_size({"width": width, "height": 900})
    page.get_by_role("button", name="Перенести данные").click()
    page.locator(".record-card--document").wait_for()
    return page.locator(".record-card--document").evaluate(
        """card => {
            const main = card.querySelector('.record-card-main');
            const style = getComputedStyle(card);
            return {
                viewport: innerWidth,
                columns: style.gridTemplateColumns,
                cardWidth: Math.round(card.getBoundingClientRect().width),
                mainWidth: Math.round(main.getBoundingClientRect().width),
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
            };
        }"""
    )


def is_full_width(measurement: dict[str, float | int | str]) -> bool:
    return (
        measurement["mainWidth"] >= measurement["cardWidth"] - 2
        and measurement["scrollWidth"] <= measurement["clientWidth"]
    )


port = free_port()
base = f"http://127.0.0.1:{port}"
server = subprocess.Popen(
    [sys.executable, "-m", "rns_import_server.app", "serve", "--port", str(port)],
    cwd=ROOT,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE,
    text=True,
)

try:
    wait_for_server(base)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")

        def mock_jobs(route):
            if route.request.method == "POST":
                route.fulfill(status=202, content_type="application/json", body='{"id":"responsive-document-card"}')
                return
            route.fulfill(status=200, content_type="application/json", body=json.dumps(public_mock_job(), ensure_ascii=False))

        page.route("**/api/jobs**", mock_jobs)
        page.goto(base)
        page.wait_for_load_state("networkidle")
        page.get_by_label("Папка с PDF").fill("C:\\public")
        page.get_by_label("Целевой файл Excel").fill("C:\\public.xlsx")

        measurements = {width: layout(page, width) for width in (1440, 480, 768)}
        print(json.dumps(measurements, ensure_ascii=False), flush=True)
        assert is_full_width(measurements[1440]), measurements[1440]
        assert is_full_width(measurements[480]), measurements[480]
        assert is_full_width(measurements[768]), measurements[768]
        browser.close()
finally:
    server.terminate()
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=5)
