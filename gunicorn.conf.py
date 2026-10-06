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

workers = int(os.environ.get("WEB_CONCURRENCY", str(multiprocessing.cpu_count() * 2 + 1)))

# Recycle workers periodically so a leak can't accumulate across many uploads.
max_requests = 1000
max_requests_jitter = 100

# Log to stdout/stderr so Coolify captures them.
accesslog = "-"
errorlog = "-"
