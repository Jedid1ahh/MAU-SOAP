"""MAU-SOAP Flask application factory.

Keeping application construction inside ``create_app`` makes the project easy
to test, configure, and run under different WSGI servers without global state.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from flask import Flask

from .extensions import db, migrate


def create_app(
    config_name: str | None = None,
    test_config: dict[str, Any] | None = None,
) -> Flask:
    """Create and configure one MAU-SOAP Flask application instance.

    Args:
        config_name: Named configuration (development, testing, or production).
            When omitted, ``FLASK_CONFIG`` selects the configuration.
        test_config: Optional dictionary used by automated tests to override
            individual settings without modifying environment variables.

    Returns:
        A fully configured Flask application with all Phase 1 blueprints and
        extensions registered.
    """

    # Load local variables before importing configuration classes. In
    # production these values should come from the hosting environment instead.
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

    return app


def _initialize_extensions(app: Flask) -> None:
    """Bind shared Flask extensions to the current app instance."""

    db.init_app(app)
    migrate.init_app(app, db)


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
