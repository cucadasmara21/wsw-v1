import subprocess
import socket
import time
import httpx


def _find_free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    addr, port = s.getsockname()
    s.close()
    return port


def _wait_for(url, timeout=5.0):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = httpx.get(url, timeout=1.0)
            if r.status_code < 500:
                return r
        except Exception:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"Timeout waiting for {url}")


def test_version_has_fields():
    port = _find_free_port()
    proc = subprocess.Popen(["python", "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)])
    try:
        res = _wait_for(f"http://127.0.0.1:{port}/version")
        assert res.status_code == 200
        data = res.json()
        assert "git_sha" in data
        assert "build_time" in data
        assert isinstance(data["git_sha"], str)
    finally:
        proc.terminate()
        proc.wait()
