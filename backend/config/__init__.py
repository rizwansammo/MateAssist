"""MateAssist Django project configuration."""

# Importing the Celery app here ensures @shared_task decorators resolve to this
# app whenever Django starts, including under manage.py and the ASGI server.
from .celery import app as celery_app

__all__ = ("celery_app",)
