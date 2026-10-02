import json
import os
import socket
import subprocess
from urllib.request import urlopen


def test_launcher_starts_and_reuses_only_its_demo():
    from app.launch import ensure_demo

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url, process = ensure_demo(port)
    try:
        with urlopen(url + "v1/capabilities", timeout=3) as response:
            assert json.load(response)["demo"] is True
        with urlopen(url + "v1/workspace", timeout=3) as response:
            assert len(json.load(response)["goals"]) == 7
        second_url, second_process = ensure_demo(port)
        assert second_url == url and second_process is None
    finally:
        if process and os.name == "nt":
            subprocess.run(["taskkill", "/pid", str(process.pid), "/t", "/f"], capture_output=True)
        elif process:
            process.terminate()
        if process:
            process.wait(timeout=5)


def test_launcher_cleans_its_process_when_readiness_times_out(monkeypatch):
    import pytest
    import app.launch as launch

    original_popen = subprocess.Popen
    started = []

    def track_process(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        started.append(process)
        return process

    monkeypatch.setattr(launch, "demo_ready", lambda url: False)
    monkeypatch.setattr(launch.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(launch.subprocess, "Popen", track_process)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    try:
        with pytest.raises(RuntimeError, match="暂未就绪"):
            launch.ensure_demo(port)
        assert started[0].poll() is not None
    finally:
        if started and started[0].poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/pid", str(started[0].pid), "/t", "/f"], capture_output=True)
            else:
                started[0].terminate()
            started[0].wait(timeout=5)
