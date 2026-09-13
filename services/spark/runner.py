"""Internal fixed-job launcher. No shell, arbitrary commands, credentials or Docker socket API."""
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

LOCK = Lock()
COMMAND = [
    "/opt/spark/bin/spark-submit", "--master", "spark://spark-master:7077",
    "--deploy-mode", "client", "--driver-memory", "512m",
    "--executor-memory", "768m", "--executor-cores", "1", "--total-executor-cores", "2",
    "--conf", "spark.driver.host=spark-runner", "--conf", "spark.driver.bindAddress=0.0.0.0",
    "--conf", "spark.cores.max=2", "--conf", "spark.ui.showConsoleProgress=false",
    "--py-files", "/opt/myleague/transform.py", "/opt/myleague/job.py",
]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/health" else 404)
        self.end_headers()

    def do_POST(self):
        if self.path != "/run":
            self.send_error(404)
            return
        if not LOCK.acquire(blocking=False):
            self.send_error(409, "Job already running")
            return
        try:
            try:
                completed = subprocess.run(COMMAND, timeout=1200, check=False)
                code = 200 if completed.returncode == 0 else 500
            except subprocess.TimeoutExpired:
                code = 504
            self.send_response(code)
            self.end_headers()
            self.wfile.write(b"Spark completed" if code == 200 else b"Spark failed: inspect runner logs")
        finally:
            LOCK.release()


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
