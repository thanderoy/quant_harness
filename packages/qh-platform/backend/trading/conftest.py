"""Pytest bootstrap. Configures Django before any test imports run.

pytest-django also reads ``DJANGO_SETTINGS_MODULE`` from
``[tool.pytest.ini_options]`` and calls ``django.setup()`` itself; doing it here
as well is idempotent and guarantees Django is configured even for non-django
collection paths.
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.config.settings")

import django  # noqa: E402

django.setup()
