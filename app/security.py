import secrets
from hmac import compare_digest

from flask import abort, request, session
from markupsafe import Markup


def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def csrf_field():
    return Markup(f'<input type="hidden" name="_csrf" value="{csrf_token()}">')


def protect_csrf():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    expected = session.get("_csrf_token", "")
    supplied = request.form.get("_csrf") or request.headers.get("X-CSRF-Token") or ""
    if not expected or not supplied or not compare_digest(expected, supplied):
        abort(400, description="Invalid CSRF token")
    return None
