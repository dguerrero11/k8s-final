"""
Task Manager — Demo App con OpenTelemetry + PostgreSQL
Bootcamp DevOps 2026 — Observabilidad en Kubernetes

Endpoints:
  GET  /           → Lista tareas (HTML)
  POST /tasks      → Crear tarea
  POST /tasks/<id>/done   → Marcar como completada
  POST /tasks/<id>/delete → Borrar tarea
  GET  /api/tasks  → Lista tareas (JSON) — ideal para demo de trazas
  GET  /health     → Health check con conexión a DB
  GET  /metrics    → Métricas Prometheus
"""

import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify, render_template_string, redirect, url_for

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from prometheus_flask_exporter import PrometheusMetrics
from prometheus_client import Counter

# ── Logging estructurado (capturado por Promtail → Loki) ──────────────────
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","service":"tasks-api","msg":"%(message)s"}'
)
logger = logging.getLogger(__name__)

# ── OpenTelemetry → Tempo ─────────────────────────────────────────────────
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "http://tempo.monitoring.svc:4318/v1/traces")
SERVICE_NAME  = os.getenv("SERVICE_NAME", "tasks-api")

resource = Resource(attributes={
    "service.name":    SERVICE_NAME,
    "service.version": os.getenv("APP_VERSION", "1.0.0"),
    "deployment.environment": os.getenv("APP_ENV", "production"),
})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT)))
trace.set_tracer_provider(provider)

# Auto-instrumentación: Flask (HTTP spans) + psycopg2 (DB spans)
FlaskInstrumentor().instrument()
Psycopg2Instrumentor().instrument()

app    = Flask(__name__)
tracer = trace.get_tracer(__name__)

# ── Métricas Prometheus → /metrics ────────────────────────────────────────
metrics = PrometheusMetrics(app)
metrics.info("tasks_app_info", "Task Manager info", version=os.getenv("APP_VERSION", "1.0.0"))

# Contadores de negocio — incrementados manualmente en cada ruta
tasks_created   = Counter("tasks_created_total",   "Total de tareas creadas")
tasks_completed = Counter("tasks_completed_total", "Total de tareas completadas")
tasks_deleted   = Counter("tasks_deleted_total",   "Total de tareas eliminadas")

# ── Conexión a PostgreSQL ─────────────────────────────────────────────────
def get_db():
    return psycopg2.connect(
        host     = os.getenv("DB_HOST",     "postgres.tasks.svc"),
        port     = int(os.getenv("DB_PORT", "5432")),
        dbname   = os.getenv("DB_NAME",     "tasksdb"),
        user     = os.getenv("DB_USER",     "tasksuser"),
        password = os.getenv("DB_PASSWORD", "taskspass"),
        cursor_factory=RealDictCursor,
        connect_timeout=5,
    )

# ── Plantilla HTML ────────────────────────────────────────────────────────
HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Task Manager — K8s Demo</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; padding: 40px 20px; }
    .container { max-width: 760px; margin: 0 auto; }
    h1  { font-size: 28px; color: #f6ad55; margin-bottom: 4px; }
    .sub { color: #718096; font-size: 13px; margin-bottom: 28px; }
    .form-row { display: flex; gap: 10px; margin-bottom: 20px; }
    input[type=text] { flex: 1; padding: 10px 14px; background: #1a1f2e; border: 1px solid #2d3748; border-radius: 8px; color: #e2e8f0; font-size: 14px; outline: none; }
    input[type=text]:focus { border-color: #f6ad55; }
    .btn        { padding: 10px 18px; border: none; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600; }
    .btn-add    { background: #f6ad55; color: #0f1117; }
    .btn-done   { background: transparent; border: 1px solid #68d391; color: #68d391; padding: 5px 10px; font-size: 12px; }
    .btn-del    { background: transparent; border: 1px solid #fc8181; color: #fc8181;  padding: 5px 10px; font-size: 12px; }
    .task-list  { display: flex; flex-direction: column; gap: 10px; }
    .task       { display: flex; align-items: center; gap: 12px; background: #1a1f2e; border: 1px solid #2d3748; border-radius: 10px; padding: 14px 18px; }
    .task.done .task-title { text-decoration: line-through; color: #4a5568; }
    .task-title { flex: 1; font-size: 14px; }
    .task-date  { font-size: 11px; color: #4a5568; min-width: 120px; text-align: right; }
    .badge      { font-size: 11px; padding: 3px 8px; border-radius: 999px; white-space: nowrap; }
    .pending    { background: #2d1500; color: #f6ad55; }
    .done-badge { background: #0d2818; color: #68d391; }
    .empty      { text-align: center; padding: 48px; color: #4a5568; font-size: 15px; }
    .stats      { display: flex; gap: 10px; margin-bottom: 20px; }
    .stat       { background: #1a1f2e; border: 1px solid #2d3748; border-radius: 8px; padding: 10px 16px; font-size: 12px; color: #a0aec0; }
    .stat b     { color: #f6ad55; font-size: 18px; display: block; }
  </style>
</head>
<body>
<div class="container">
  <h1>📋 Task Manager</h1>
  <div class="sub">Demo · Kubernetes Bootcamp 2026 · namespace: tasks · db: PostgreSQL · trazas: Tempo</div>

  <div class="stats">
    <div class="stat"><b>{{ tasks | length }}</b> total</div>
    <div class="stat"><b>{{ tasks | selectattr('done','equalto',False) | list | length }}</b> pendientes</div>
    <div class="stat"><b>{{ tasks | selectattr('done') | list | length }}</b> completadas</div>
  </div>

  <form class="form-row" method="POST" action="/tasks">
    <input type="text" name="title" placeholder="Nueva tarea..." required autocomplete="off">
    <button type="submit" class="btn btn-add">+ Agregar</button>
  </form>

  <div class="task-list">
    {% if tasks %}
      {% for t in tasks %}
      <div class="task {% if t.done %}done{% endif %}">
        <span class="badge {% if t.done %}done-badge{% else %}pending{% endif %}">
          {% if t.done %}✓ done{% else %}pending{% endif %}
        </span>
        <span class="task-title">{{ t.title }}</span>
        <span class="task-date">{{ t.created_at.strftime('%Y-%m-%d %H:%M') }}</span>
        {% if not t.done %}
        <form method="POST" action="/tasks/{{ t.id }}/done" style="margin:0">
          <button type="submit" class="btn btn-done">✓</button>
        </form>
        {% endif %}
        <form method="POST" action="/tasks/{{ t.id }}/delete" style="margin:0">
          <button type="submit" class="btn btn-del">✕</button>
        </form>
      </div>
      {% endfor %}
    {% else %}
      <div class="empty">No hay tareas. ¡Agrega la primera! 🚀</div>
    {% endif %}
  </div>
</div>
</body>
</html>
"""

# ── Rutas ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Lista todas las tareas — genera span HTTP + span DB automáticamente"""
    with tracer.start_as_current_span("list-all-tasks") as span:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM tasks ORDER BY created_at DESC")
                tasks = cur.fetchall()
            span.set_attribute("tasks.count", len(tasks))
            logger.info(f"Listed {len(tasks)} tasks")
        finally:
            conn.close()
    return render_template_string(HTML, tasks=tasks)


@app.route("/tasks", methods=["POST"])
def create_task():
    """Crear tarea — span con atributo task.title"""
    title = request.form.get("title", "").strip()
    if not title:
        return redirect(url_for("index"))
    with tracer.start_as_current_span("create-task") as span:
        span.set_attribute("task.title", title)
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO tasks (title) VALUES (%s) RETURNING id",
                    (title,)
                )
                task_id = cur.fetchone()["id"]
                conn.commit()
            span.set_attribute("task.id", task_id)
            tasks_created.inc()
            logger.info(f"Created task id={task_id} title={title!r}")
        finally:
            conn.close()
    return redirect(url_for("index"))


@app.route("/tasks/<int:task_id>/done", methods=["POST"])
def complete_task(task_id):
    """Completar tarea — span con task.id"""
    with tracer.start_as_current_span("complete-task") as span:
        span.set_attribute("task.id", task_id)
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE tasks SET done=TRUE WHERE id=%s", (task_id,))
                conn.commit()
            tasks_completed.inc()
            logger.info(f"Completed task id={task_id}")
        finally:
            conn.close()
    return redirect(url_for("index"))


@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
def delete_task(task_id):
    """Eliminar tarea"""
    with tracer.start_as_current_span("delete-task") as span:
        span.set_attribute("task.id", task_id)
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tasks WHERE id=%s", (task_id,))
                conn.commit()
            tasks_deleted.inc()
            logger.info(f"Deleted task id={task_id}")
        finally:
            conn.close()
    return redirect(url_for("index"))


@app.route("/api/tasks")
def api_tasks():
    """API JSON — ideal para curl y ver trazas en Tempo"""
    with tracer.start_as_current_span("api-list-tasks") as span:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, title, done, created_at::text FROM tasks ORDER BY created_at DESC"
                )
                tasks = [dict(t) for t in cur.fetchall()]
            span.set_attribute("tasks.count", len(tasks))
            return jsonify({"tasks": tasks, "total": len(tasks), "service": SERVICE_NAME})
        finally:
            conn.close()


@app.route("/health")
def health():
    """Health check — verifica conexión a PostgreSQL"""
    with tracer.start_as_current_span("health-check") as span:
        try:
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS total FROM tasks")
                row = cur.fetchone()
            conn.close()
            span.set_attribute("db.tasks_total", row["total"])
            return jsonify({"status": "ok", "db": "connected", "tasks": row["total"]})
        except Exception as e:
            span.record_exception(e)
            logger.error(f"Health check failed: {e}")
            return jsonify({"status": "error", "db": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
