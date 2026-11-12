import os
from datetime import timedelta
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from .models import db

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)

def create_app(config=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY'),
        SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///agentgrade.db'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False, MAX_CONTENT_LENGTH=192 * 1024,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', 'true').lower() == 'true',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        RATELIMIT_STORAGE_URI=os.environ.get('RATE_LIMIT_STORAGE_URI', 'memory://'))
    if config:
        app.config.update(config)
    if not app.config.get('SECRET_KEY') or len(app.config['SECRET_KEY']) < 32:
        raise RuntimeError('Set a random SECRET_KEY of at least 32 characters.')
    if os.environ.get('TRUST_PROXY') == 'true':
        # Enable only behind the supplied private Caddy ingress, never on a public app port.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    from .web import bp
    app.register_blueprint(bp)
    from .cli import register
    register(app)
    @app.after_request
    def headers(response):
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Cache-Control'] = 'no-store'
        if app.config['SESSION_COOKIE_SECURE']:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response
    return app
