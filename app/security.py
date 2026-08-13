"""Validasi runtime dan hardening HTTP untuk aplikasi Flask."""

from __future__ import annotations

import secrets

from flask import g, jsonify, request
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix


DEVELOPMENT_SECRET = "development-only-change-me"
VALID_ENVIRONMENTS = frozenset({"development", "testing", "production"})


class ProductionConfigurationError(RuntimeError):
    """Konfigurasi produksi tidak aman atau belum lengkap."""


def _normalize_environment(app):
    environment = str(app.config.get("APP_ENV", "development")).strip().lower()
    if environment not in VALID_ENVIRONMENTS:
        raise ProductionConfigurationError(
            "APP_ENV harus development, testing, atau production."
        )
    app.config["APP_ENV"] = environment
    if environment == "production":
        app.config.update(
            SESSION_COOKIE_SECURE=True,
            PREFERRED_URL_SCHEME="https",
            ENABLE_HSTS=True,
        )
    return environment


def _validate_common_config(app):
    maximum_length = app.config.get("MAX_CONTENT_LENGTH")
    if not isinstance(maximum_length, int) or maximum_length < 1024:
        raise ProductionConfigurationError(
            "MAX_CONTENT_LENGTH harus berupa integer minimal 1.024 byte."
        )


def _validate_production_config(app):
    errors = []
    secret_key = app.config.get("SECRET_KEY")
    if (
        not isinstance(secret_key, str)
        or len(secret_key) < 32
        or secret_key == DEVELOPMENT_SECRET
    ):
        errors.append("SECRET_KEY produksi wajib acak dan minimal 32 karakter")
    if app.config.get("DEBUG"):
        errors.append("FLASK_DEBUG wajib false pada produksi")
    if not app.config.get("GOOGLE_MAPS_BROWSER_API_KEY"):
        errors.append("GOOGLE_MAPS_BROWSER_API_KEY wajib diisi")
    if not app.config.get("GOOGLE_MAPS_SERVER_API_KEY"):
        errors.append("GOOGLE_MAPS_SERVER_API_KEY wajib diisi")
    if app.config.get("GOOGLE_MAPS_MAP_ID") in {None, "", "DEMO_MAP_ID"}:
        errors.append("GOOGLE_MAPS_MAP_ID produksi wajib memakai Map ID sendiri")
    trusted_hosts = app.config.get("TRUSTED_HOSTS")
    if not isinstance(trusted_hosts, (list, tuple)) or not trusted_hosts:
        errors.append("TRUSTED_HOSTS produksi wajib diisi")
    contact_email = app.config.get("PUBLIC_CONTACT_EMAIL")
    if not isinstance(contact_email, str) or "@" not in contact_email:
        errors.append("PUBLIC_CONTACT_EMAIL produksi wajib berupa email")
    if errors:
        raise ProductionConfigurationError(
            "Konfigurasi produksi belum valid: " + "; ".join(errors) + "."
        )


def _content_security_policy(nonce):
    """CSP nonce mengikuti pola strict CSP untuk Maps JavaScript API."""

    return " ".join(
        (
            "default-src 'self';",
            (
                f"script-src 'nonce-{nonce}' 'strict-dynamic' https: "
                "'unsafe-eval' blob:;"
            ),
            (
                "img-src 'self' https://*.googleapis.com "
                "https://*.gstatic.com *.google.com *.googleusercontent.com "
                "data: blob:;"
            ),
            "frame-src *.google.com;",
            (
                "connect-src 'self' https://*.googleapis.com *.google.com "
                "https://*.gstatic.com data: blob:;"
            ),
            "font-src 'self' https://fonts.gstatic.com;",
            (
                f"style-src 'self' 'nonce-{nonce}' "
                "https://fonts.googleapis.com;"
            ),
            "worker-src blob:;",
            "object-src 'none';",
            "base-uri 'self';",
            "form-action 'self';",
            "frame-ancestors 'none';",
        )
    )


def _api_error(code, message, status_code):
    return (
        jsonify(
            {
                "status": "error",
                "error": {"code": code, "message": message},
            }
        ),
        status_code,
    )


def _register_error_handlers(app):
    @app.errorhandler(413)
    def request_too_large(error):
        if request.path.startswith("/api/"):
            return _api_error(
                "payload_too_large",
                "Body permintaan melebihi batas ukuran yang diizinkan.",
                413,
            )
        return error

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return _api_error(
                "not_found",
                "Endpoint API tidak ditemukan.",
                404,
            )
        return error

    @app.errorhandler(405)
    def method_not_allowed(error):
        if request.path.startswith("/api/"):
            return _api_error(
                "method_not_allowed",
                "Metode HTTP tidak diizinkan untuk endpoint ini.",
                405,
            )
        return error

    @app.errorhandler(500)
    def internal_server_error(error):
        if request.path.startswith("/api/"):
            return _api_error(
                "internal_error",
                "Terjadi kesalahan internal pada sistem.",
                500,
            )
        if isinstance(error, HTTPException):
            return error
        return "Terjadi kesalahan internal pada sistem.", 500


def configure_application_security(app):
    """Memvalidasi konfigurasi dan memasang kontrol keamanan aplikasi."""

    environment = _normalize_environment(app)
    _validate_common_config(app)
    if environment == "production":
        _validate_production_config(app)

    if app.config.get("USE_PROXY_FIX"):
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=1,
            x_proto=1,
            x_host=1,
        )

    @app.before_request
    def create_content_security_nonce():
        g.csp_nonce = secrets.token_urlsafe(18)

    @app.after_request
    def apply_security_headers(response):
        nonce = getattr(g, "csp_nonce", secrets.token_urlsafe(18))
        response.headers["Content-Security-Policy"] = (
            _content_security_policy(nonce)
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), geolocation=(), microphone=()"
        )
        if app.config["ENABLE_HSTS"]:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    _register_error_handlers(app)
