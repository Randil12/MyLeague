FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /srv/webapp
RUN useradd --uid 10001 --create-home webapp
USER 10001
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/healthz', timeout=3)" || exit 1
CMD ["uvicorn", "webapp.server:app", "--host", "0.0.0.0", "--port", "8501", "--no-proxy-headers"]
