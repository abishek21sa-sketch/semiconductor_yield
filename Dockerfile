# ---- Stage 1: build the React frontend ----
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/index.html frontend/vite.config.js ./
COPY frontend/src/ src/
RUN npm run build

# ---- Stage 2: the actual app ----
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pipeline/ pipeline/
COPY api/ api/
COPY data/ data/
COPY alembic/ alembic/
COPY alembic.ini .
COPY --from=frontend-build /app/frontend/dist/ frontend/dist/

# No GRB_LICENSE_FILE set by default: Gurobi then falls back to its bundled
# size-limited free tier (2000 vars/constraints). The small single-week
# release-mix MILP (~10 vars) fits inside it, but pipeline/capacity_plan.py
# and pipeline/bottleneck_scheduler.py build much larger MILPs (thousands of
# variables) that genuinely need a real academic/commercial license -- they
# degrade gracefully to {"status": "license_required"} without one. To use a
# real license, set GRB_LICENSE_FILE and mount the file -- see
# docker-compose.yml and DEPLOYMENT.md.

EXPOSE 8020

# start-period is long because the app pre-warms the full real-data pipeline
# (yield model + all 4 scenarios: SimPy Monte Carlo + Gurobi) on startup.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8020/api/health')" || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8020"]
