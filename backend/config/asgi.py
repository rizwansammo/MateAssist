"""ASGI entrypoint (D-003).

ASGI rather than WSGI because chat responses stream to the browser over SSE
(D-041); a synchronous worker would buffer the whole completion.

    backend\\.venv\\Scripts\\python.exe -m uvicorn config.asgi:application --reload
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_asgi_application()
