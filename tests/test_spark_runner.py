"""Launcher contract tests without Docker, JVM or production data."""
import importlib.util
import io
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("spark_runner", ROOT / "services/spark/runner.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def handler(path="/run"):
    instance = object.__new__(runner.Handler)
    instance.path = path
    instance.send_response = Mock()
    instance.send_error = Mock()
    instance.end_headers = Mock()
    instance.wfile = io.BytesIO()
    return instance


def test_fixed_distributed_command():
    assert "spark://spark-master:7077" in runner.COMMAND
    assert "local[*]" not in runner.COMMAND
    assert runner.COMMAND[runner.COMMAND.index("--total-executor-cores") + 1] == "2"
    assert runner.COMMAND[runner.COMMAND.index("--executor-cores") + 1] == "1"
    assert not any("password" in part for part in runner.COMMAND)


def test_success(monkeypatch):
    launch = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(runner.subprocess, "run", launch)
    h = handler()
    h.do_POST()
    h.send_response.assert_called_once_with(200)
    launch.assert_called_once_with(runner.COMMAND, timeout=1200, check=False)
    assert not runner.LOCK.locked()


def test_failed_process(monkeypatch):
    monkeypatch.setattr(runner.subprocess, "run", Mock(return_value=SimpleNamespace(returncode=1)))
    h = handler()
    h.do_POST()
    h.send_response.assert_called_once_with(500)
    assert not runner.LOCK.locked()


def test_timeout(monkeypatch):
    monkeypatch.setattr(runner.subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("spark", 1200)))
    h = handler()
    h.do_POST()
    h.send_response.assert_called_once_with(504)
    assert not runner.LOCK.locked()


def test_concurrent_request():
    runner.LOCK.acquire()
    try:
        h = handler()
        h.do_POST()
        h.send_error.assert_called_once_with(409, "Job already running")
    finally:
        runner.LOCK.release()


def test_unknown_path():
    h = handler("/arbitrary-command")
    h.do_POST()
    h.send_error.assert_called_once_with(404)
