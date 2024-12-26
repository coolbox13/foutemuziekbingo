from flask import Blueprint, request, current_app


def log_request_info():
    """Centralized request logging for all routes."""
    current_app.logger.info("Headers: %s", request.headers)
    current_app.logger.info("Body: %s", request.get_data())


bp = Blueprint("routes", __name__)


@bp.before_request
def before_request():
    log_request_info()


def register_blueprints(app):
    """Register all blueprints to the Flask application."""
    app.logger.info("Registering blueprints.")

    from app.auth_routes import bp as auth_bp
    from app.dashboard_routes import bp as dashboard_bp
    from app.playlist_routes import bp as playlist_bp
    from app.device_routes import bp as device_bp
    from app.card_routes import bp as card_bp
    from app.playback_routes import bp as playback_bp
    from app.game_routes import bp as game_bp

    # Register all blueprints with their prefixes
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(playlist_bp, url_prefix="/playlist")
    app.register_blueprint(device_bp, url_prefix="/device")
    app.register_blueprint(card_bp, url_prefix="/card")
    app.register_blueprint(playback_bp, url_prefix="/playback")
    app.register_blueprint(game_bp, url_prefix="/game")
