#!/usr/bin/env python
"""Django management entrypoint.

Run through the venv interpreter directly rather than relying on an activated
shell, so scripts and CI behave identically to an interactive session:

    backend\\.venv\\Scripts\\python.exe backend\\manage.py <command>
"""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Django is not importable. The venv is probably not the interpreter "
            "running this file - use backend\\.venv\\Scripts\\python.exe."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
