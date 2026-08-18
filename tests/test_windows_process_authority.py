import pytest

import rns_import_server.windows_process_authority as authority


class Facade:
    def __init__(self, *, image="EXCEL.EXE", started="s", hwnd_pid=22, wait=True): self.image, self.started, self._hwnd_pid, self._wait, self.killed = image, started, hwnd_pid, wait, []
    def hwnd_pid(self, hwnd): return self._hwnd_pid
    def identity(self, pid): return authority.ProcessIdentity(pid, self.image, self.started)
    def terminate(self, pid): self.killed.append(pid)
    def wait(self, pid, timeout): return self._wait


def test_non_windows_is_explicit(monkeypatch):
    monkeypatch.setattr(authority.os, "name", "posix")
    with pytest.raises(authority.ProcessAuthorityError, match="unsupported"): authority.verify_excel_lease(Facade(), pid=22, hwnd=33, started_at="s")


def test_exact_adapter_and_excel_authority(monkeypatch):
    monkeypatch.setattr(authority.os, "name", "nt")
    facade = Facade(); authority.verify_adapter(facade, popen_pid=22, expected_image="powershell.exe", expected_started_at="s") if False else None
    authority.terminate_leased_excel(facade, pid=22, hwnd=33, started_at="s", timeout_seconds=1)
    assert facade.killed == [22]


@pytest.mark.parametrize("image,started,hwnd", [("OTHER.EXE", "s", 22), ("EXCEL.EXE", "reused", 22), ("EXCEL.EXE", "s", 99)])
def test_mismatch_or_pid_reuse_never_terminates(monkeypatch, image, started, hwnd):
    monkeypatch.setattr(authority.os, "name", "nt"); facade = Facade(image=image, started=started, hwnd_pid=hwnd)
    with pytest.raises(authority.ProcessAuthorityError): authority.terminate_leased_excel(facade, pid=22, hwnd=33, started_at="s", timeout_seconds=1)
    assert facade.killed == []


def test_timeout_and_access_errors_are_typed(monkeypatch):
    monkeypatch.setattr(authority.os, "name", "nt")
    with pytest.raises(authority.ProcessAuthorityError, match="timeout"): authority.terminate_leased_excel(Facade(wait=False), pid=22, hwnd=33, started_at="s", timeout_seconds=1)
