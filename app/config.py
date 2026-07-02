import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-for-production")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(BASE_DIR / 'data' / 'hrm.sqlite').as_posix()}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    COMPANY_NAME = os.getenv("COMPANY_NAME", "Employee Portal Co.")
    PORTAL_NAME = os.getenv("PORTAL_NAME", "Employee Portal")

    UPLOAD_FOLDER = os.getenv(
        "UPLOAD_FOLDER", str(BASE_DIR / "app" / "static" / "uploads")
    )
    PROFILE_UPLOAD_SUBDIR = str(Path(UPLOAD_FOLDER) / "profiles")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_MB", "6")) * 1024 * 1024
    PHOTO_MAX_SIZE = (900, 900)

    AUTO_SEED = env_bool("AUTO_SEED", True)
    SEED_JSON_PATH = os.getenv(
        "SEED_JSON_PATH", str(BASE_DIR / "seed" / "employees.json")
    )

    OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "")
    OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "")
    OIDC_DISCOVERY_URL = os.getenv(
        "OIDC_DISCOVERY_URL",
        "https://sso.akashdth.com/application/o/hrm-portal/.well-known/openid-configuration",
    )
    OIDC_SCOPE = os.getenv("OIDC_SCOPE", "openid email profile groups")
    OIDC_LOGOUT_URL = os.getenv("OIDC_LOGOUT_URL", "")

    ADMIN_EMAILS = env_list("ADMIN_EMAILS")
    ADMIN_GROUPS = env_list("ADMIN_GROUPS", "HRM Admins,hrm-admins")

    DEV_LOGIN_ENABLED = env_bool("DEV_LOGIN_ENABLED", False)
    TRUST_PROXY = env_bool("TRUST_PROXY", False)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = int(os.getenv("SESSION_LIFETIME_SECONDS", "28800"))

    # SMTP configuration
    MAIL_SERVER = os.getenv("MAIL_SERVER", "192.168.151.76")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "25"))
    MAIL_USE_TLS = env_bool("MAIL_USE_TLS", False)
    MAIL_USE_SSL = env_bool("MAIL_USE_SSL", False)
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "employee.portal@akashdth.com")

