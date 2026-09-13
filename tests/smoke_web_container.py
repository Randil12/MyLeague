"""Run via stdin inside the built Docker image; never connects to a real DB."""

import json
import subprocess
import time
import urllib.error
import urllib.request

process = subprocess.Popen([
    "uvicorn", "webapp.server:app", "--host", "127.0.0.1", "--port", "8501",
])
try:
    for attempt in range(40):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8501/healthz", timeout=1) as response:
                assert json.load(response)["status"] == "ok"
            break
        except urllib.error.URLError:
            time.sleep(.2)
    else:
        raise AssertionError("Server did not start")
    for path in ("/", "/static/app.js", "/static/style.css"):
        with urllib.request.urlopen("http://127.0.0.1:8501" + path, timeout=2) as response:
            assert response.status == 200
    try:
        urllib.request.urlopen("http://127.0.0.1:8501/api/patches", timeout=5)
    except urllib.error.HTTPError as exc:
        assert exc.code == 503
        assert "detail" in json.load(exc)
    else:
        raise AssertionError("Offline container must report unavailable database")
    print("Docker read-only smoke: HTTP/assets OK; database failure handled (503)")
finally:
    process.terminate()
    process.wait(timeout=5)
