# Web process that runs migrations and starts the application
#release: flask db upgrade
web: gunicorn --config gunicorn_config.py app:app

# Alternative web process if using start.py for migrations
#web: python start.py

# If you need a worker process (e.g., for background tasks)
# worker: celery -A app.celery worker --loglevel=info