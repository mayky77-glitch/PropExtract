from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading

from rns_import_server.new_row import NewRowCode, NewRowPublicationResult, NewRowRequest, NewRowService
from rns_import_server.workbook_groups import SheetProjection, SheetRow


class Pending:
    def __init__(self): self.lock = threading.Lock(); self.reserved = False
    def reserve_pending_to_publishing(self, action_id, *, job_authorization):
        with self.lock:
            if self.reserved: return False
            self.reserved = True; return True
    def reopen_after_pre_hash_failure(self, action_id, *, job_authorization): return True


class Projection:
    def read_projection(self): return SheetProjection.from_rows("book", "hash", 1, (SheetRow(1, d="Стройка"), SheetRow(2, is_business_row=True, is_preformatted=True), SheetRow(3, d="Другая")))


class Publisher:
    def __init__(self): self.calls = 0; self.lock = threading.Lock()
    def publish(self, publication):
        with self.lock: self.calls += 1
        return NewRowPublicationResult(True)


def test_concurrent_submit_reserves_once_and_calls_publisher_once() -> None:
    pending, publisher = Pending(), Publisher()
    service = NewRowService(projections=Projection(), pending=pending, publisher=publisher)
    request = NewRowRequest("action", "job", "c", "Стройка", "123-1234567", "0001", "Объект", "RU-12345678-09-2026", ("Стройка", "Другая"))
    with ThreadPoolExecutor(max_workers=2) as executor:
        codes = list(executor.map(lambda _: service.submit(request).code, range(2)))
    assert sorted(codes) == [NewRowCode.PENDING_ALREADY_RESERVED, NewRowCode.PLANNED]
    assert publisher.calls == 1
