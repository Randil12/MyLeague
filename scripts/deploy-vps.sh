#!/usr/bin/env bash
# Existing, provisioned VPS only. Never overwrite .env or initialize databases.
set -euo pipefail
commit="${1:?Expected tested commit SHA}"
[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || exit 2
cd /home/ubuntu/MyLeague
test -f .env
git diff --quiet
git diff --cached --quiet
git fetch origin
git cat-file -e "$commit^{commit}"
previous="$(git rev-parse HEAD)"
git merge --ff-only "$commit"
test "$(git rev-parse HEAD)" = "$commit"
printf 'Deploying %s (previous commit: %s)\n' "$commit" "$previous"
docker compose --profile spark config --quiet
# Build the shared Spark tag only once.
docker compose --profile spark build web riot-live spark-master
docker compose --profile spark up -d --no-build --pull never --no-deps \
  web riot-live spark-master spark-worker-1 spark-worker-2 spark-runner
docker compose restart airflow
for attempt in $(seq 1 36); do
  if docker compose exec -T web python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/healthz', timeout=3)" \
    && docker compose exec -T spark-runner python3 -c \
    "import json,urllib.request; d=json.load(urllib.request.urlopen('http://spark-master:8080/json/',timeout=3)); assert sum(w['state']=='ALIVE' for w in d['workers'])==2" \
    && docker compose exec -T riot-live python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8091/roster',timeout=5)"; then
      printf 'Deployment health checks passed for %s\n' "$commit"
      exit 0
  fi
  sleep 5
done
printf 'Deployment health checks failed. Inspect VPS logs. Previous commit: %s\n' "$previous" >&2
exit 1
