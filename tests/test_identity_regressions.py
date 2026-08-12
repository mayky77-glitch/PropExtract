"""Synthetic regressions for bounded RNS identity recovery."""
from __future__ import annotations

from pathlib import Path

from rns_import_server.ocr import OCRLine, OCRText, OCRWord
from rns_import_server.rns_adapter import _clean_district, extract, norm


LABELED_RNS = "38-03-06-2025"
UNRELATED_RNS = "RU-12345678-09-2026"


def _geometry_text(value: str) -> OCRText:
    words = tuple(
        OCRWord(word, 20 + index * 100, 40, max(20, len(word) * 8), 20, 95.0)
        for index, word in enumerate(value.split())
    )
    return OCRText(value, (OCRLine(1, 1600, 2200, words),))


def test_unique_labeled_rns_wins_over_unrelated_global_identity():
    text = f"""Номер разрешения на строительство: {LABELED_RNS}
Дата выдачи: 01.02.2025
Справочный номер: {UNRELATED_RNS}
"""

    assert norm(Path("unrelated.pdf"), text) == LABELED_RNS
    record = extract(Path("unrelated.pdf"), text)
    assert record is not None
    assert record["number"] == LABELED_RNS
    assert record["number_source"] == "content"


def test_reordered_semantic_label_line_recovers_exact_form_identity():
    labeled_line = f"|-2. строительство: Номер разрешения на [{LABELED_RNS}"
    text = _geometry_text(labeled_line)

    assert norm(Path("unrelated.pdf"), text) == LABELED_RNS
    record = extract(Path("unrelated.pdf"), text)
    assert record is not None
    assert record["number"] == LABELED_RNS
    assert record["number_source"] == "content"


def test_reordered_semantic_label_wins_only_on_its_own_line():
    text = f"""строительство: Номер разрешения на [{LABELED_RNS}
Справочный номер: {UNRELATED_RNS}
"""

    assert norm(Path("unrelated.pdf"), text) == LABELED_RNS


def test_ambiguous_labeled_rns_stays_unidentified_without_filename_fallback():
    text = f"Номер разрешения на строительство: {LABELED_RNS}; {UNRELATED_RNS}"
    filename = Path("38-07-02-2025.pdf")

    assert norm(filename, text) is None
    assert extract(filename, text) is None


def test_multiple_labeled_rns_values_stay_unidentified_without_filename_fallback():
    text = f"""Номер разрешения на строительство: {LABELED_RNS}
Номер разрешения на строительство: {UNRELATED_RNS}
"""
    filename = Path("38-07-02-2025.pdf")

    assert norm(filename, text) is None
    assert extract(filename, text) is None


def test_two_identities_on_one_reordered_semantic_label_line_are_ambiguous():
    text = f"строительство: Номер разрешения на [{LABELED_RNS}; {UNRELATED_RNS}"
    filename = Path("38-07-02-2025.pdf")

    assert norm(filename, text) is None
    assert extract(filename, text) is None


def test_repeated_semantic_label_lines_are_ambiguous_even_after_identity_dedupe():
    text = f"""строительство: Номер разрешения на [{LABELED_RNS}
2. строительство: Номер разрешения на [{LABELED_RNS}
"""

    assert norm(Path("unrelated.pdf"), text) is None
    assert extract(Path("unrelated.pdf"), text) is None


def test_semantic_tokens_split_across_global_narrative_do_not_form_label_evidence():
    text = f"""Номер документа указан ниже.
Текст описывает разрешение без реквизита.
Отдельно упомянуто строительство объекта: {LABELED_RNS}.
Справочный идентификатор: {UNRELATED_RNS}.
"""
    filename = Path("38-07-02-2025.pdf")

    assert norm(filename, text) is None
    assert extract(filename, text) is None


def test_narrative_reference_with_all_label_words_does_not_override_global_ambiguity():
    text = f"""Для справки указан номер разрешения прежнего строительства: {LABELED_RNS}.
Основной реквизит документа: {UNRELATED_RNS}.
"""
    filename = Path("38-07-02-2025.pdf")

    assert norm(filename, text) is None
    assert extract(filename, text) is None


def test_unlabeled_global_ambiguity_stays_unidentified_without_filename_fallback():
    text = f"Основной номер {LABELED_RNS}; справочный номер {UNRELATED_RNS}"
    filename = Path("38-07-02-2025.pdf")

    assert norm(filename, text) is None
    assert extract(filename, text) is None


def test_unlabeled_unique_global_rns_remains_compatible():
    text = f"Основной номер {LABELED_RNS}"

    assert norm(Path("unrelated.pdf"), text) == LABELED_RNS


def test_district_cleanup_removes_proven_dangling_fragments_without_collapsing_multiple_districts():
    assert _clean_district("Жигаловский район составе") == "Жигаловский район"
    assert _clean_district("Иркутская область Жигаловский в") == "Жигаловский район"
    assert _clean_district("Жигаловский, Казачинско-Ленский районы") == "Жигаловский, Казачинско-Ленский районы"
    assert _clean_district("Жигаловский район в составе муниципального образования") == "Жигаловский район в составе муниципального образования"
