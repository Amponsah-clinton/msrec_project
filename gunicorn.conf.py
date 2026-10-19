"""Gunicorn configuration for the MSREC deployment (Coolify / Nixpacks).

Start the app with:  gunicorn config.wsgi:application -c gunicorn.conf.py

Why this file exists: submitting an application uploads its documents to
Supabase Storage synchronously, inside the request (applicant_dashboard/
storage.py, up to 30s per file). Gunicorn's default 30s worker timeout kills
that request mid-upload, and the applicant's browser shows a bare
net::ERR_FAILED on the submit. A generous timeout lets a multi-document
submission finish instead of being cut off.
"""
import multiprocessing
import os

# Bind to the port the host assigns (Coolify/Nixpacks set $PORT); 8000 local.
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# The actual fix: well above the worst-case sum of per-file upload timeouts.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
# Slow document uploads can hold a connection open; keep-alive a touch higher.
keepalive = 10

# Each worker is its own process with its own database connection, so the
# worker count is also a database-connection count. Supabase's pooler caps
# clients at the project's pool_size (15 by default), and the unbounded
# cpu_count() * 2 + 1 default walks straight through it: 9 workers on a
# 4-core host, 17 on an 8-core one -- which exhausts the cap on its own,
# giving "(EMAXCONNSESSION) max clients reached in session mode" before any
# other client connects. Capped here so a bigger host can't silently take
# the database down with it; raise WEB_CONCURRENCY deliberately (and only
# when DATABASE_URL points at the :6543 transaction pooler, which shares
# backend connections -- see config/settings.py).
_cpu_default = min(multiprocessing.cpu_count() * 2 + 1, 5)
workers = int(os.environ.get("WEB_CONCURRENCY", str(_cpu_default)))

# Recycle workers periodically so a leak can't accumulate across many uploads.
max_requests = 1000
max_requests_jitter = 100

# Log to stdout/stderr so Coolify captures them.
accesslog = "-"
errorlog = "-"
