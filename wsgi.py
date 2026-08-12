"""WSGI entry point used by the Flask CLI and, later, Gunicorn."""

from app import create_app

app = create_app()


if __name__ == "__main__":
    # The development server is convenient locally but must not be used in
    # production; Phase 12 will run this app through Gunicorn and Nginx.
    app.run()

