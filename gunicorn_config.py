# gunicorn_config.py
import multiprocessing

# Worker configurations
workers = 2  # Reduce number of workers for memory-intensive tasks
worker_class = 'sync'
threads = 4
worker_connections = 1000
timeout = 600  # 10 minutes timeout
keepalive = 2

# Server configurations
bind = "0.0.0.0:$PORT"  # Railway provides the PORT environment variable
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# SSL (if needed)
keyfile = None
certfile = None

# Prevent worker timeout
graceful_timeout = 120