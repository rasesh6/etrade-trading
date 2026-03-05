# Gunicorn configuration for Railway
import os

# Bind to port from environment
bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"

# Worker configuration
# MUST be 1 for SSE + order monitoring singleton to work correctly.
# gevent handles concurrency via green threads within a single process.
workers = 1
worker_class = "gevent"
worker_connections = 100
timeout = 120
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
