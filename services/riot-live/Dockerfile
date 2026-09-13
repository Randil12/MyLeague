FROM python:3.12-slim
WORKDIR /srv
COPY services/riot-live/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY jobs/ /srv/jobs/
RUN useradd --create-home --uid 10002 spectator
USER 10002
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PGCONNECT_TIMEOUT=5 AWS_MAX_ATTEMPTS=2 AWS_RETRY_MODE=standard
HEALTHCHECK --start-period=180s --interval=30s --timeout=5s CMD python -c "import json,time; from pathlib import Path; assert time.time() < json.loads(Path('/tmp/myleague-live-heartbeat').read_text())['deadline']" || exit 1
CMD ["python", "-m", "jobs.riot.live_service"]
