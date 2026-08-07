"""WSGI entrypoint.

Retained for tooling that expects it. The served application is ASGI (D-003) -
SSE streaming does not work through WSGI.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_wsgi_application()
