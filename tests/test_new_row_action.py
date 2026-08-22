from __future__ import annotations

from rns_import_server.new_row import NewRowCode, NewRowRequest, NewRowService
from rns_import_server.workbook_groups import SheetProjection, SheetRow


class Pending:
    def reserve_pending_to_publishing(self, action_id, *, job_authorization): return True
    def reopen_after_pre_hash_failure(self, action_id, *, job_authorization): return True
    def close_existing(self, action_id, *, job_authorization, terminal_state, observed_row, observed_workbook_hash): return object()


class Projection:
    def read_projection(self):
        return SheetProjection.from_rows("book", "hash", 1, (SheetRow(1, d="Стройка"), SheetRow(2, is_business_row=True, is_preformatted=True), SheetRow(3, d="Другая")))


class Publisher:
    def __init__(self): self.calls = 0
    def publish(self, publication):
        self.calls += 1
        from rns_import_server.new_row import NewRowPublicationResult
        return NewRowPublicationResult(True)


def request(suffix="0001", name="Объект"):
    return NewRowRequest("action", "job", "c", "Стройка", "123-1234567", suffix, name, "RU-12345678-09-2026", ("Стройка", "Другая"))


def test_ascii_suffix_builds_server_code_and_rejects_unicode_width_sign_and_whitespace() -> None:
    publisher = Publisher(); service = NewRowService(projections=Projection(), pending=Pending(), publisher=publisher)
    accepted = service.submit(request())
    assert accepted.code is NewRowCode.PLANNED and accepted.object_code == "123-1234567.0001"
    for invalid in ("１２３４", "+001", " 001", "0001 ", "١٢٣٤"):
        assert service.submit(request(invalid)).code is NewRowCode.INVALID_SUFFIX
    assert publisher.calls == 1


def test_equal_name_duplicate_is_allowed_but_different_name_is_exact_conflict() -> None:
    class DuplicateProjection:
        def read_projection(self):
            return SheetProjection.from_rows("book", "hash", 1, (SheetRow(1, d="Стройка"), SheetRow(2, c="123-1234567.0001", d="Объект"), SheetRow(3, is_business_row=True, is_preformatted=True), SheetRow(4, d="Другая")))
    publisher = Publisher(); service = NewRowService(projections=DuplicateProjection(), pending=Pending(), publisher=publisher)
    assert service.submit(request()).code is NewRowCode.PLANNED
    assert service.submit(request(name="Другое")).code is NewRowCode.OBJECT_CODE_NAME_CONFLICT
    assert publisher.calls == 1


def test_existing_row_closes_without_publisher_and_distinguishes_exact_code_name() -> None:
    class ExistingProjection:
        def __init__(self, code): self.code = code
        def read_projection(self):
            return SheetProjection.from_rows("book", "a" * 64, 1, (
                SheetRow(1, d="Стройка"), SheetRow(2, c=self.code, d="Объект", f="RU-12345678-09-2026"), SheetRow(3, d="Другая"),
            ))
    class Closing(Pending):
        def __init__(self): self.states = []
        def close_existing(self, action_id, **kwargs): self.states.append(kwargs["terminal_state"]); return object()
    publisher, pending = Publisher(), Closing()
    service = NewRowService(projections=ExistingProjection("123-1234567.0001"), pending=pending, publisher=publisher)
    assert service.submit(request()).code is NewRowCode.RESOLVED_EXISTING
    review = NewRowService(projections=ExistingProjection("123-1234567"), pending=pending, publisher=publisher)
    assert review.submit(request()).code is NewRowCode.EXISTING_REVIEW
    assert pending.states == ["resolved_existing", "existing_review"] and publisher.calls == 0
