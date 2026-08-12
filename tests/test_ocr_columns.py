from pathlib import Path
from types import SimpleNamespace

from rns_import_server import ocr
from rns_import_server.ocr import OCRLine, OCRText, OCRWord, _tsv_text
from rns_import_server.rns_adapter import _clean_district, extract


def _line(page_width: int, top: int, left: str = "", right: str = "", skew: int = 0) -> OCRLine:
    words: list[OCRWord] = []
    x = 120 + skew
    for text in left.split():
        width = max(24, len(text) * 9)
        words.append(OCRWord(text, x, top, width, 22, 95.0))
        x += width + 12
    x = 820 + skew
    for text in right.split():
        width = max(24, len(text) * 9)
        words.append(OCRWord(text, x, top, width, 22, 95.0))
        x += width + 12
    return OCRLine(1, page_width, 2100, tuple(words))


def test_geometry_uses_left_label_but_returns_only_slanted_right_column():
    lines = (
        _line(1500, 30, right="Тестовая администрация", skew=1),
        _line(1500, 65, "1.3. Наименование органа (организации):", "муниципального района", 3),
        _line(1500, 100, "1.4. Срок действия", "05.01.2027", 5),
        _line(1500, 140, "Раздел 3. Информация об объекте"),
        _line(1500, 180, right="Синтетический", skew=9),
        _line(1500, 215, right="объект", skew=13),
        _line(1500, 250, "3.1. Наименование объекта капитального", "правой колонки", 17),
        _line(1500, 285, "строительства в соответствии", "и его продолжение", 21),
        _line(1500, 320, "с проектной документацией:"),
        _line(1500, 360, "3.2. Вид выполняемых работ", "строительство", 29),
    )
    plain = "\n".join(line.text for line in lines)
    text = OCRText("38-1-1-2026\n" + plain, lines)

    record = extract(Path("permit.pdf"), text)

    assert record is not None
    assert record["issuer"] == "Тестовая администрация муниципального района"
    assert record["object"] == "Синтетический объект правой колонки и его продолжение"


def test_tsv_parser_keeps_plain_text_and_word_geometry():
    tsv = "\n".join(
        (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "1\t1\t0\t0\t0\t0\t0\t0\t1500\t2100\t-1\t",
            "5\t1\t1\t1\t1\t1\t120\t100\t90\t22\t96.5\tМетка",
            "5\t1\t1\t1\t1\t2\t820\t100\t100\t22\t94.0\tЗначение",
        )
    )

    parsed = _tsv_text(tsv)

    assert parsed == "Метка Значение"
    assert len(parsed.lines) == 1
    assert parsed.lines[0].page_width == 1500
    assert [word.text for word in parsed.lines[0].words] == ["Метка", "Значение"]


def test_geometry_ocr_uses_project_models_and_tsv_output(monkeypatch):
    calls = []
    monkeypatch.setattr(ocr, "tesseract_environment", lambda: {"TESSDATA_PREFIX": "/project/tessdata"})

    def run(argv, *, timeout, env=None):
        calls.append((argv, timeout, env))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(ocr, "_run", run)

    assert ocr._ocr_image(Path("page.png"), "project-tesseract") == ""
    argv, timeout, environment = calls[0]
    assert argv[0] == "project-tesseract"
    assert argv[-2:] == ["-c", "tessedit_create_tsv=1"]
    assert timeout == 120
    assert environment == {"TESSDATA_PREFIX": "/project/tessdata"}


def test_tesseract_environment_limits_openmp_unless_operator_set(monkeypatch):
    monkeypatch.setattr(ocr, "bundled_language_status", lambda: {"rus": {"valid": True}, "eng": {"valid": True}})
    monkeypatch.delenv("OMP_THREAD_LIMIT", raising=False)

    assert ocr.tesseract_environment()["OMP_THREAD_LIMIT"] == "1"

    monkeypatch.setenv("OMP_THREAD_LIMIT", "4")
    assert ocr.tesseract_environment()["OMP_THREAD_LIMIT"] == "4"


def test_render_uses_grayscale_to_reduce_temporary_image_memory(monkeypatch, tmp_path):
    pdf = tmp_path / "form.pdf"
    pdf.write_bytes(b"pdf")
    commands = []
    monkeypatch.setattr(ocr, "page_count", lambda path: 1)
    monkeypatch.setattr(ocr, "_text_layer", lambda path, last_page: None)
    monkeypatch.setattr(ocr, "find_tool", lambda name: name)
    def run(argv, *, timeout, env=None):
        commands.append(argv)
        image = Path(argv[-1] + "-1.png")
        image.write_bytes(b"png")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(ocr, "_run", run)
    monkeypatch.setattr(ocr, "_ocr_image", lambda image, executable: OCRText("text"))

    text, pages = ocr.read(pdf)

    assert text == "text" and pages == 1
    assert commands[0][:5] == ["pdftoppm", "-png", "-gray", "-r", "180"]


def test_explicit_extension_filename_overrides_stale_scanned_validity():
    text = """38-07-04-2025
1.1. Дата разрешения на строительство: 28.03.2025
1.4. Срок действия настоящего разрешения: 28.11.2025
"""

    extended = extract(
        Path("Разрешение 3807042025 — продление до 28.11.2026года.pdf"),
        text,
    )
    ordinary = extract(Path("Разрешение 3807042025 до 28.11.2026.pdf"), text)

    assert extended is not None
    assert extended["end"] == "28.11.2026"
    assert extended["field_provenance"]["end"] == "filename"
    assert ordinary is not None
    assert ordinary["end"] == "28.11.2025"


def test_district_cleanup_removes_split_label_tail_and_adds_field_type():
    assert _clean_district("округ, |Казачинско-Ленский муниципальный район") == "Казачинско-Ленский район"
    assert _clean_district("Казачинско-Ленский") == "Казачинско-Ленский район"
    assert _clean_district("Жигаловский, Казачинско-Ленский районы") == "Жигаловский, Казачинско-Ленский районы"
