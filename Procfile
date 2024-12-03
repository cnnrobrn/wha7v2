# Web process that runs migrations and starts the application
#release: flask db upgrade
web: gunicorn --timeout=$GUNICORN_TIMEOUT --workers=$GUNICORN_WORKERS --threads=$GUNICORN_THREADS --worker-class=$GUNICORN_WORKER_CLASS --worker-connections=$GUNICORN_WORKER_CONNECTIONS --max-requests=$GUNICORN_MAX_REQUESTS --max-requests-jitter=$GUNICORN_MAX_REQUESTS_JITTER --graceful-timeout=$GUNICORN_GRACEFUL_TIMEOUT app:app
# Alternative web process if using start.py for migrations
#web: python start.py

# If you need a worker process (e.g., for background tasks)
# worker: celery -A app.celery worker --loglevel=info