"""MAU-SOAP Flask application factory.

Keeping application construction inside ``create_app`` makes the project easy
to test, configure, and run under different WSGI servers without global state.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from flask import Flask

from .extensions import bcrypt, db, migrate


def create_app(
    config_name: str | None = None,
    test_config: dict[str, Any] | None = None,
) -> Flask:
    """Create and configure one MAU-SOAP Flask application instance."""

    load_dotenv()

    from .config import CONFIG_BY_NAME, validate_configuration

    selected_config = config_name or os.getenv("FLASK_CONFIG", "development")
    if selected_config not in CONFIG_BY_NAME:
        valid_names = ", ".join(sorted(CONFIG_BY_NAME))
        raise ValueError(
            f"Unknown FLASK_CONFIG '{selected_config}'. Expected one of: {valid_names}."
        )

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(CONFIG_BY_NAME[selected_config])

    if test_config:
        app.config.update(test_config)

    validate_configuration(app.config)
    _initialize_extensions(app)
    _register_blueprints(app)
    _register_commands(app)

    return app


def _initialize_extensions(app: Flask) -> None:
    """Bind shared Flask extensions to the current app instance."""

    from .models import MODEL_REGISTRY

    if not MODEL_REGISTRY:  # pragma: no cover
        raise RuntimeError("No database models were registered.")

    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)


def _register_blueprints(app: Flask) -> None:
    """Register route groups while keeping the factory concise."""

    from .admin import admin_bp
    from .api import api_bp
    from .candidate import candidate_bp
    from .main import main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(candidate_bp, url_prefix="/exam")
    app.register_blueprint(api_bp, url_prefix="/api/v1")


def _register_commands(app: Flask) -> None:
    """Register maintenance commands on Flask's application CLI."""

    from .cli import seed_db_command

    app.cli.add_command(seed_db_command)