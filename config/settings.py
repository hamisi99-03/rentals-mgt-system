"""Django settings for the offline rentals management desktop app."""

import os
import sys
from pathlib import Path

from django.core.management.utils import get_random_string

APP_VERSION = "1.0.0"

# Code and bundled assets. In a PyInstaller build this is the temporary _MEIPASS.
CODE_DIR = Path(__file__).resolve().parent.parent
BASE_DIR = Path(getattr(sys, "_MEIPASS", CODE_DIR)) if getattr(sys, "frozen", False) else CODE_DIR


def _default_data_dir() -> Path:
    env_dir = os.environ.get("RENTALS_DATA_DIR")
    if env_dir:
        return Path(env_dir)
    if getattr(sys, "frozen", False):
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local) / "RentalsManager"
    return CODE_DIR


# User data lives outside the install folder in a packaged build.
DATA_DIR = _default_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)

# The app is fully offline. Persist a generated secret so sessions survive restarts.
_SECRET_FILE = DATA_DIR / "instance" / "secret_key.txt"


def _load_secret_key() -> str:
    env_key = os.environ.get("RENTALS_SECRET_KEY")
    if env_key:
        return env_key
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_text(encoding="utf-8").strip()
    _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    key = get_random_string(50)
    _SECRET_FILE.write_text(key, encoding="utf-8")
    return key


SECRET_KEY = _load_secret_key()

DEBUG = os.environ.get("RENTALS_DEBUG", "1") == "1"

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1:8765", "http://localhost:8765"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "core",
    "property",
    "billing",
    "payments",
    "operations",
    "reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.CurrentUserMiddleware",
    "core.middleware.IdleLockMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.app_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20},
        "TEST": {"NAME": DATA_DIR / "instance" / "test_db.sqlite3"},
    }
}

AUTH_USER_MODEL = "core.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = DATA_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = DATA_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# pywebview runs on localhost; hide the app from the network.
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
X_FRAME_OPTIONS = "DENY"

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "app.log"),
            "maxBytes": 2_000_000,
            "backupCount": 3,
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console", "file"], "level": "INFO"},
}
