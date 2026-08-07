"""Celery application.

Start the worker with the venv interpreter directly:
    backend\\.venv\\Scripts\\python.exe -m celery -A config worker -l info -P solo

-P solo on Windows: the default prefork pool does not work there. Production
(Linux containers, D-140) uses the default pool.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("mateassist")

# All Celery settings live in Django settings under the CELERY_ prefix, so the
# repo-root .env stays the single source of truth.
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, name="core.ping")
def ping(self) -> str:
    """Trivial round-trip task used to prove broker wiring end to end."""
    return "pong"
