# ── Stage 1: dependencias ─────────────────────────────────────────────────
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: imagen final ─────────────────────────────────────────────────
FROM python:3.11-slim
WORKDIR /app

# Copiar dependencias instaladas
COPY --from=builder /install /usr/local

# Copiar código fuente
COPY app.py .

# Usuario no-root
RUN useradd -r -u 1001 appuser && chown -R appuser /app
USER 1001

EXPOSE 8080

# Gunicorn: 2 workers, logs a stdout (capturados por Promtail)
CMD ["gunicorn", \
     "--workers=2", \
     "--bind=0.0.0.0:8080", \
     "--access-logfile=-", \
     "--error-logfile=-", \
     "--log-level=info", \
     "--timeout=30", \
     "app:app"]
