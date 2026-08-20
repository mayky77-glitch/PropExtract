from __future__ import annotations

import pytest

import rns_import_server.windows_process_authority as authority


class FakeFacade:
    def __init__(
        self,
        *,
        image: str = r"C:\\Program Files\\Microsoft Office\\EXCEL.EXE",
        started: str = "2026-08-18T01:02:03Z",
        hwnd_pid: int = 22,
        identity_pid: int = 22,
        wait: bool = True,
        open_error: BaseException | None = None,
        identity_error: BaseException | None = None,
    ) -> None:
        self.image, self.started = image, started
        self._hwnd_pid, self.identity_pid, self._wait = hwnd_pid, identity_pid, wait
        self.open_error, self.identity_error = open_error, identity_error
        self.opened: list[tuple[int, bool, object]] = []
        self.identities: list[object] = []
        self.terminated: list[object] = []
        self.waited: list[tuple[object, float]] = []
        self.closed: list[object] = []

    def hwnd_pid(self, hwnd: int) -> int:
        return self._hwnd_pid

    def open_process(self, pid: int, *, terminate: bool) -> object:
        if self.open_error:
            raise self.open_error
        handle = object()
        self.opened.append((pid, terminate, handle))
        return handle

    def identity_from_handle(self, handle: object, pid: int) -> authority.ProcessIdentity:
        self.identities.append(handle)
        if self.identity_error:
            raise self.identity_error
        return authority.ProcessIdentity(self.identity_pid, self.image, self.started)

    def terminate_handle(self, handle: object) -> None:
        self.terminated.append(handle)

    def wait_handle(self, handle: object, timeout_seconds: float) -> bool:
        self.waited.append((handle, timeout_seconds))
        return self._wait

    def close_handle(self, handle: object) -> None:
        self.closed.append(handle)


@pytest.fixture(autouse=True)
def windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(authority.os, "name", "nt")


def test_non_windows_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(authority.os, "name", "posix")
    with pytest.raises(authority.ProcessAuthorityError, match="unsupported"):
        authority.verify_excel_lease(FakeFacade(), pid=22, hwnd=33, started_at="s")


def test_adapter_identity_uses_exact_popen_pid_and_closes_query_handle() -> None:
    facade = FakeFacade(image=r"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe")
    identity = authority.verify_adapter(
        facade, popen_pid=22, expected_image="powershell.exe", expected_started_at="2026-08-18T01:02:03Z",
    )
    assert identity.pid == 22
    assert facade.opened[0][:2] == (22, False)
    assert facade.closed == [facade.opened[0][2]]
    mismatched_pid = FakeFacade(image="powershell.exe", identity_pid=23)
    with pytest.raises(authority.ProcessAuthorityError, match="adapter_identity_mismatch"):
        authority.verify_adapter(mismatched_pid, popen_pid=22, expected_image="powershell.exe", expected_started_at="2026-08-18T01:02:03Z")
    assert mismatched_pid.closed == [mismatched_pid.opened[0][2]]


def test_cleanup_revalidates_and_uses_one_handle_for_terminate_wait_close() -> None:
    facade = FakeFacade()
    authority.terminate_leased_excel(facade, pid=22, hwnd=33, started_at="2026-08-18T01:02:03Z", timeout_seconds=1)
    handle = facade.opened[0][2]
    assert facade.opened[0][:2] == (22, True)
    assert facade.identities == [handle]
    assert facade.terminated == [handle]
    assert facade.waited == [(handle, 1)]
    assert facade.closed == [handle]


@pytest.mark.parametrize(
    "facade",
    [
        FakeFacade(image="OTHER.EXE"),
        FakeFacade(started="pid-reused"),
        FakeFacade(hwnd_pid=99),
        FakeFacade(identity_pid=99),
    ],
)
def test_mismatch_or_pid_reuse_never_terminates_and_closes_open_handle(facade: FakeFacade) -> None:
    with pytest.raises(authority.ProcessAuthorityError):
        authority.terminate_leased_excel(facade, pid=22, hwnd=33, started_at="2026-08-18T01:02:03Z", timeout_seconds=1)
    assert facade.terminated == []
    assert facade.closed == [facade.opened[0][2]]


def test_access_denied_and_vanished_never_terminate_or_leak_handles() -> None:
    denied = FakeFacade(open_error=PermissionError("denied"))
    with pytest.raises(authority.ProcessAuthorityError, match="process_access_denied"):
        authority.terminate_leased_excel(denied, pid=22, hwnd=33, started_at="2026-08-18T01:02:03Z", timeout_seconds=1)
    assert denied.terminated == denied.closed == []
    vanished = FakeFacade(identity_error=ProcessLookupError("gone"))
    with pytest.raises(authority.ProcessAuthorityError, match="process_vanished"):
        authority.terminate_leased_excel(vanished, pid=22, hwnd=33, started_at="2026-08-18T01:02:03Z", timeout_seconds=1)
    assert vanished.terminated == []
    assert vanished.closed == [vanished.opened[0][2]]


def test_timeout_is_typed_and_handle_is_closed_after_termination() -> None:
    facade = FakeFacade(wait=False)
    with pytest.raises(authority.ProcessAuthorityError, match="excel_termination_timeout"):
        authority.terminate_leased_excel(facade, pid=22, hwnd=33, started_at="2026-08-18T01:02:03Z", timeout_seconds=1)
    assert facade.terminated == [facade.opened[0][2]]
    assert facade.closed == [facade.opened[0][2]]


def test_typed_win32_last_error_maps_access_denied() -> None:
    facade = FakeFacade(open_error=authority.Win32ApiError("open_process", 5))
    with pytest.raises(authority.ProcessAuthorityError) as error:
        authority.verify_excel_lease(facade, pid=22, hwnd=33, started_at="2026-08-18T01:02:03Z")
    assert error.value.code == "process_access_denied"
    assert error.value.winerror == 5
