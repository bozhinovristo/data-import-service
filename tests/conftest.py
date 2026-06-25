"""Shared test configuration.

Sets dummy environment variables *before* any test module (and therefore
`src.config`, which validates env at import time) is imported, so the suite is
hermetic and never depends on a real `.env` file. Real environment variables, if
present, take precedence over these defaults.
"""

import os

os.environ.setdefault("API_BASE_URL", "http://testserver")
os.environ.setdefault("API_CLIENT_ID", "test-client-id")
os.environ.setdefault("API_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("API_USERNAME", "test-user")
os.environ.setdefault("API_PASSWORD", "test-pass")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
