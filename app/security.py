"""Validasi runtime dan hardening HTTP untuk aplikasi Flask."""

from __future__ import annotations

import ipaddress
import math
import re
import secrets

from flask import g, jsonify, request
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix


DEVELOPMENT_SECRET = "development-only-change-me"
VALID_ENVIRONMENTS = frozenset({"development", "testing", "production"})
HOST_LABEL_PATTERN = re.compile(
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
    flags=re.IGNORECASE,
)
EMAIL_LOCAL_PATTERN = re.compile(
    r"[a-z0-9!#$%&'*+/=?^_`{|}~.-]+",
    flags=re.IGNORECASE,
)


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
    quota_limits = {
        "GOOGLE_COMPUTE_ROUTES_DAILY_LIMIT": 100,
        "GOOGLE_ROUTE_MATRIX_DAILY_ELEMENT_LIMIT": 2000,
        "GOOGLE_COMPUTE_ROUTES_PER_MINUTE_LIMIT": 100,
        "GOOGLE_ROUTE_MATRIX_PER_MINUTE_ELEMENT_LIMIT": 2000,
        "GOOGLE_WEB_MAX_COMPUTE_ROUTES_PER_REQUEST": 2,
        "GOOGLE_WEB_MAX_MATRIX_ELEMENTS_PER_REQUEST": 625,
    }
    for name, maximum in quota_limits.items():
        value = app.config.get(name)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 1 <= value <= maximum
        ):
            raise ProductionConfigurationError(
                f"{name} harus berupa integer 1 sampai {maximum}."
            )
    if (
        app.config["GOOGLE_WEB_MAX_COMPUTE_ROUTES_PER_REQUEST"]
        > app.config["GOOGLE_COMPUTE_ROUTES_DAILY_LIMIT"]
    ):
        raise ProductionConfigurationError(
            "Batas Compute Routes per request tidak boleh melebihi batas "
            "harian."
        )
    if (
        app.config["GOOGLE_WEB_MAX_MATRIX_ELEMENTS_PER_REQUEST"]
        > app.config["GOOGLE_ROUTE_MATRIX_DAILY_ELEMENT_LIMIT"]
    ):
        raise ProductionConfigurationError(
            "Batas elemen Matrix per request tidak boleh melebihi batas "
            "harian."
        )
    if (
        app.config["GOOGLE_WEB_MAX_COMPUTE_ROUTES_PER_REQUEST"]
        > app.config["GOOGLE_COMPUTE_ROUTES_PER_MINUTE_LIMIT"]
    ):
        raise ProductionConfigurationError(
            "Batas Compute Routes per request tidak boleh melebihi batas "
            "per menit."
        )
    if (
        app.config["GOOGLE_WEB_MAX_MATRIX_ELEMENTS_PER_REQUEST"]
        > app.config["GOOGLE_ROUTE_MATRIX_PER_MINUTE_ELEMENT_LIMIT"]
    ):
        raise ProductionConfigurationError(
            "Batas elemen Matrix per request tidak boleh melebihi batas "
            "per menit."
        )

    numeric_config = {
        "DEFAULT_SOC_MIN": app.config.get("DEFAULT_SOC_MIN"),
        "DEFAULT_SOC_TARGET": app.config.get("DEFAULT_SOC_TARGET"),
        "DEFAULT_CURRENT_SOC": app.config.get("DEFAULT_CURRENT_SOC"),
        "DEFAULT_MAXIMUM_RANGE_KM": app.config.get(
            "DEFAULT_MAXIMUM_RANGE_KM"
        ),
        "DEFAULT_SAFETY_FACTOR": app.config.get("DEFAULT_SAFETY_FACTOR"),
        "DEFAULT_CORRIDOR_RADIUS_KM": app.config.get(
            "DEFAULT_CORRIDOR_RADIUS_KM"
        ),
        "DEFAULT_ROUTE_SAMPLE_STEP_KM": app.config.get(
            "DEFAULT_ROUTE_SAMPLE_STEP_KM"
        ),
        "DEFAULT_SOC_STEP": app.config.get("DEFAULT_SOC_STEP"),
        "GOOGLE_ROUTES_TIMEOUT_SECONDS": app.config.get(
            "GOOGLE_ROUTES_TIMEOUT_SECONDS"
        ),
    }
    for name, value in numeric_config.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ProductionConfigurationError(
                f"{name} harus berupa angka finite."
            )

    minimum_soc = float(numeric_config["DEFAULT_SOC_MIN"])
    target_soc = float(numeric_config["DEFAULT_SOC_TARGET"])
    if not 0 <= minimum_soc < 100:
        raise ProductionConfigurationError(
            "DEFAULT_SOC_MIN harus berada pada rentang 0 sampai kurang dari 100."
        )
    if not minimum_soc < target_soc <= 100:
        raise ProductionConfigurationError(
            "DEFAULT_SOC_TARGET harus lebih besar dari DEFAULT_SOC_MIN dan "
            "maksimal 100."
        )
    current_soc = float(numeric_config["DEFAULT_CURRENT_SOC"])
    if not minimum_soc < current_soc <= 100:
        raise ProductionConfigurationError(
            "DEFAULT_CURRENT_SOC harus lebih besar dari DEFAULT_SOC_MIN dan "
            "maksimal 100."
        )
    if not 0 < float(numeric_config["DEFAULT_MAXIMUM_RANGE_KM"]) <= 2000:
        raise ProductionConfigurationError(
            "DEFAULT_MAXIMUM_RANGE_KM harus berada pada rentang >0 sampai "
            "2.000 km."
        )
    if not 0 < float(numeric_config["DEFAULT_SAFETY_FACTOR"]) <= 1:
        raise ProductionConfigurationError(
            "DEFAULT_SAFETY_FACTOR harus berada pada rentang >0 sampai 1."
        )
    if not 0 < float(numeric_config["DEFAULT_CORRIDOR_RADIUS_KM"]) <= 100:
        raise ProductionConfigurationError(
            "DEFAULT_CORRIDOR_RADIUS_KM harus berada pada rentang >0 sampai 100."
        )
    if not 0.1 <= float(
        numeric_config["DEFAULT_ROUTE_SAMPLE_STEP_KM"]
    ) <= 100:
        raise ProductionConfigurationError(
            "DEFAULT_ROUTE_SAMPLE_STEP_KM harus berada pada rentang 0,1 "
            "sampai 100."
        )
    if not 0 < float(numeric_config["DEFAULT_SOC_STEP"]) <= 100 - minimum_soc:
        raise ProductionConfigurationError(
            "DEFAULT_SOC_STEP harus lebih besar dari nol dan tidak melebihi "
            "rentang SOC yang tersedia."
        )
    if not 0 < float(numeric_config["GOOGLE_ROUTES_TIMEOUT_SECONDS"]) <= 120:
        raise ProductionConfigurationError(
            "GOOGLE_ROUTES_TIMEOUT_SECONDS harus berada pada rentang >0 "
            "sampai 120."
        )


def _normalized_required_text(app, name, error_message, errors):
    value = app.config.get(name)
    if not isinstance(value, str) or not value.strip():
        errors.append(error_message)
        return None
    normalized = value.strip()
    app.config[name] = normalized
    return normalized


def _normalize_trusted_host(value):
    """Menormalisasi hostname/IP tanpa menerima URL, path, wildcard, atau port."""

    if not isinstance(value, str) or not value.strip():
        return None
    host = value.strip().lower()
    suffix_match = host.startswith(".")
    if suffix_match:
        host = host[1:]
    if not host or any(character in host for character in "/:@"):
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        try:
            ascii_host = host.encode("idna").decode("ascii")
        except UnicodeError:
            return None
        if len(ascii_host) > 253:
            return None
        labels = ascii_host.split(".")
        if (
            any(not HOST_LABEL_PATTERN.fullmatch(label) for label in labels)
            or all(label.isdigit() for label in labels)
        ):
            return None
        if suffix_match and len(labels) < 2:
            return None
        normalized = ascii_host
    else:
        if suffix_match or address.version != 4:
            return None
        normalized = str(address)
    return f".{normalized}" if suffix_match else normalized


def _normalize_contact_email(value):
    """Validasi konservatif untuk alamat kontak publik produksi."""

    if not isinstance(value, str):
        return None
    email = value.strip()
    if not email or len(email) > 254 or email.count("@") != 1:
        return None
    local_part, domain = email.rsplit("@", 1)
    if (
        not local_part
        or len(local_part) > 64
        or local_part.startswith(".")
        or local_part.endswith(".")
        or ".." in local_part
        or not EMAIL_LOCAL_PATTERN.fullmatch(local_part)
    ):
        return None
    normalized_domain = _normalize_trusted_host(domain)
    if (
        normalized_domain is None
        or normalized_domain.startswith(".")
        or "." not in normalized_domain
    ):
        return None
    top_level_domain = normalized_domain.rsplit(".", 1)[1]
    if not (
        top_level_domain.isalpha()
        or top_level_domain.startswith("xn--")
    ):
        return None
    try:
        ipaddress.ip_address(normalized_domain)
    except ValueError:
        pass
    else:
        return None
    return f"{local_part}@{normalized_domain}"


def _validate_production_config(app):
    errors = []
    secret_key = _normalized_required_text(
        app,
        "SECRET_KEY",
        "SECRET_KEY produksi wajib acak dan minimal 32 karakter",
        errors,
    )
    if secret_key is not None and (
        len(secret_key) < 32
        or any(character.isspace() for character in secret_key)
        or secret_key == DEVELOPMENT_SECRET
    ):
        errors.append("SECRET_KEY produksi wajib acak dan minimal 32 karakter")
    if app.config.get("DEBUG"):
        errors.append("FLASK_DEBUG wajib false pada produksi")
    browser_key = _normalized_required_text(
        app,
        "GOOGLE_MAPS_BROWSER_API_KEY",
        "GOOGLE_MAPS_BROWSER_API_KEY wajib diisi",
        errors,
    )
    server_key = _normalized_required_text(
        app,
        "GOOGLE_MAPS_SERVER_API_KEY",
        "GOOGLE_MAPS_SERVER_API_KEY wajib diisi",
        errors,
    )
    if browser_key is not None and browser_key == server_key:
        errors.append("browser key dan server key wajib berbeda")
    map_id = _normalized_required_text(
        app,
        "GOOGLE_MAPS_MAP_ID",
        "GOOGLE_MAPS_MAP_ID produksi wajib memakai Map ID sendiri",
        errors,
    )
    if map_id == "DEMO_MAP_ID":
        errors.append("GOOGLE_MAPS_MAP_ID produksi wajib memakai Map ID sendiri")
    trusted_hosts = app.config.get("TRUSTED_HOSTS")
    if not isinstance(trusted_hosts, (list, tuple)) or not trusted_hosts:
        errors.append("TRUSTED_HOSTS produksi wajib diisi")
    else:
        normalized_hosts = [
            _normalize_trusted_host(host) for host in trusted_hosts
        ]
        if any(host is None for host in normalized_hosts):
            errors.append(
                "TRUSTED_HOSTS hanya boleh memuat hostname atau IPv4 yang valid"
            )
        else:
            app.config["TRUSTED_HOSTS"] = list(
                dict.fromkeys(normalized_hosts)
            )
    contact_email = _normalize_contact_email(
        app.config.get("PUBLIC_CONTACT_EMAIL")
    )
    if contact_email is None:
        errors.append("PUBLIC_CONTACT_EMAIL produksi wajib berupa email")
    else:
        app.config["PUBLIC_CONTACT_EMAIL"] = contact_email
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
