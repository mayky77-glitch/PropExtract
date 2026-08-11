"""Contract checks for local server identity and launcher lifecycle handling."""
from __future__ import annotations

import errno
import json
import re
import socket
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

from rns_import_server import app, server


def _unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _runner(*args: object, **kwargs: object) -> dict[str, object]:
    return {}


def test_project_instance_id_is_opaque_and_stable_per_copy(tmp_path: Path):
    first = server.project_instance_id(tmp_path / "copy-one")
    second = server.project_instance_id(tmp_path / "copy-two")

    assert first == server.project_instance_id(tmp_path / "copy-one")
    assert first != second
    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert str(tmp_path) not in first


def test_health_returns_only_opaque_instance_identity():
    port = _unused_port()
    instance_id = "a" * 64
    httpd = server.create_server("127.0.0.1", port, _runner, instance_id=instance_id)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
            health = json.loads(response.read().decode("utf-8"))
            response_instance_id = response.headers["X-PropExtract-Instance"]
        assert health == {"status": "ok", "service": "rns-import"}
        assert response_instance_id == instance_id
        assert "/" not in response_instance_id and "\\" not in response_instance_id
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_server_refuses_non_loopback_bind():
    with pytest.raises(ValueError, match="loopback"):
        server.create_server("0.0.0.0", _unused_port(), _runner)


def test_file_retry_has_deadline_and_reraises_last_oserror(monkeypatch):
    now = [0.0]
    errors: list[OSError] = []

    def operation():
        error = PermissionError(errno.EACCES, "share lock")
        errors.append(error)
        raise error

    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(server.time, "sleep", lambda delay: now.__setitem__(0, now[0] + delay))

    with pytest.raises(OSError) as raised:
        server.retry_file_operation(operation, attempts=20, deadline=0.5, initial_delay=0.2)

    assert raised.value is errors[-1]
    assert len(errors) == 2
    assert now[0] == 0.5


def test_bind_error_is_russian_and_preserves_os_diagnostic(monkeypatch, capsys):
    def fail_bind(*args: object, **kwargs: object):
        raise OSError(errno.EADDRINUSE, "Address already in use")

    monkeypatch.setattr(server, "create_server", fail_bind)
    monkeypatch.setattr(sys, "argv", ["app.py", "serve", "--host", "127.0.0.1", "--port", "8775"])

    with pytest.raises(SystemExit) as stopped:
        app.main()

    assert stopped.value.code == 1
    stderr = capsys.readouterr().err
    assert "Не удалось запустить" in stderr
    assert "Address already in use" in stderr


def test_open_browser_happens_only_after_server_binds(monkeypatch):
    events: list[str] = []

    class BoundServer:
        def serve_forever(self):
            events.append("serving")

    def create_bound_server(*args: object, **kwargs: object):
        events.append("bound")
        return BoundServer()

    monkeypatch.setattr(server, "create_server", create_bound_server)
    monkeypatch.setattr(app.webbrowser, "open", lambda url: events.append(f"browser:{url}"))
    monkeypatch.setattr(sys, "argv", ["app.py", "serve", "--open-browser"])

    app.main()

    assert events == ["bound", "browser:http://127.0.0.1:8775", "serving"]


def test_windows_scripts_require_same_instance_and_wait_before_browser():
    root = Path(__file__).parents[1]
    start = (root / "start_windows.ps1").read_text(encoding="utf-8")
    stop = (root / "stop_windows.ps1").read_text(encoding="utf-8")

    assert "project_instance_id" in start and "instance_id -eq $InstanceId" in start
    assert "X-PropExtract-Instance" in start and "X-PropExtract-Instance" in stop
    assert "Start-Process -FilePath" not in start
    assert "--open-browser" in start
    assert start.isascii() and stop.isascii()
    assert "instance_id -ne $InstanceId" in stop
    assert "while ([DateTime]::UtcNow -lt $Deadline)" in stop
    assert "Get-PropExtractMessage \"wrong\"" in stop
