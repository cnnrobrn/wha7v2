import subprocess
from flask import Flask
from flask.cli import FlaskGroup
from app import app  # Import your main app

def run_migrations():
    try:
        # Run Flask migrations
        subprocess.run(['flask', 'db', 'upgrade'], check=True)
        print("Migrations completed successfully")
    except subprocess.CalledProcessError as e:
        print(f"Error running migrations: {e}")
        raise

if __name__ == '__main__':
    # Run migrations first
    run_migrations()
    
    # Then start the application
    app.run(host='0.0.0.0', port=5000)