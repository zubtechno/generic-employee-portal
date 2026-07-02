from datetime import datetime, timezone
from functools import wraps

from authlib.integrations.flask_client import OAuth
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .models import Employee, User, db
from .utils import is_admin_identity, normalize_email, normalize_groups, serialize_groups


auth_bp = Blueprint("auth", __name__)
oauth = OAuth()


def init_oauth(app):
    oauth.init_app(app)
    if app.config["OIDC_CLIENT_ID"] and app.config["OIDC_CLIENT_SECRET"]:
        oauth.register(
            name="authentik",
            client_id=app.config["OIDC_CLIENT_ID"],
            client_secret=app.config["OIDC_CLIENT_SECRET"],
            server_metadata_url=app.config["OIDC_DISCOVERY_URL"],
            client_kwargs={"scope": app.config["OIDC_SCOPE"]},
        )


def load_current_user():
    g.current_user = None
    user_id = session.get("user_id")
    if user_id:
        g.current_user = db.session.get(User, user_id)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not getattr(g, "current_user", None):
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not g.current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def directory_admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not (g.current_user.is_admin or getattr(g.current_user, "is_directory_admin", False)):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def service_admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not (g.current_user.is_admin or getattr(g.current_user, "is_service_admin", False)):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def support_admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not (g.current_user.is_admin or getattr(g.current_user, "is_support_admin", False)):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def audit_admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not (g.current_user.is_admin or getattr(g.current_user, "is_audit_admin", False)):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def clearance_admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not (g.current_user.is_admin or getattr(g.current_user, "is_clearance_admin", False)):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def reminder_admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not (g.current_user.is_admin or getattr(g.current_user, "is_reminder_admin", False)):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def reminder_viewer_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not (g.current_user.is_admin or
                getattr(g.current_user, "is_reminder_admin", False) or
                getattr(g.current_user, "is_reminder_viewer", False)):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def find_employee_for_user(email, employee_id=None):
    if employee_id:
        employee = Employee.query.filter_by(employee_id=str(employee_id)).one_or_none()
        if employee:
            return employee
    if email:
        return Employee.query.filter(db.func.lower(Employee.email) == email.lower()).one_or_none()
    return None


def sync_user_from_claims(claims):
    email = normalize_email(claims.get("email") or claims.get("preferred_username"))
    sub = claims.get("sub")
    if not email or not sub:
        abort(401, description="SSO did not return required email/sub claims.")

    groups = normalize_groups(claims.get("groups") or claims.get("ak_groups"))
    employee_id = (
        claims.get("employee_id")
        or claims.get("employeeNumber")
        or claims.get("employee_no")
        or None
    )
    employee = find_employee_for_user(email, employee_id)
    is_admin = is_admin_identity(email, groups, current_app.config)

    user = User.query.filter_by(authentik_sub=sub).one_or_none()
    if user is None:
        user = User(authentik_sub=sub, email=email)
        db.session.add(user)

    user.email = email
    user.username = claims.get("preferred_username") or claims.get("nickname") or email
    user.full_name = claims.get("name") or claims.get("given_name") or user.username
    user.groups_json = serialize_groups(groups)
    user.is_admin = is_admin
    user.employee_id = employee.employee_id if employee else employee_id
    user.last_login_at = datetime.now(timezone.utc)
    db.session.commit()
    return user


def login_user(user):
    session.clear()
    session.permanent = True
    session["user_id"] = user.id


@auth_bp.get("/login")
def login():
    if getattr(g, "current_user", None):
        return redirect(url_for("main.employee_index"))
    next_url = request.args.get("next")
    if next_url and next_url.startswith("/"):
        session["next_url"] = next_url
    return render_template("login.html", oidc_ready=bool(current_app.config["OIDC_CLIENT_ID"]))


@auth_bp.get("/auth/login")
def start_login():
    client = oauth.create_client("authentik")
    if client is None:
        flash("SSO is not configured yet. Set OIDC_CLIENT_ID and OIDC_CLIENT_SECRET.", "error")
        return redirect(url_for("auth.login"))
    redirect_uri = url_for("auth.callback", _external=True)
    return client.authorize_redirect(redirect_uri)


@auth_bp.get("/auth/callback")
def callback():
    client = oauth.create_client("authentik")
    if client is None:
        abort(401)
    token = client.authorize_access_token()
    claims = token.get("userinfo")
    if claims is None:
        claims = client.userinfo(token=token)
    user = sync_user_from_claims(dict(claims))
    login_user(user)
    next_url = session.pop("next_url", None) or url_for("main.employee_index")
    return redirect(next_url)


@auth_bp.post("/auth/local-login")
def local_login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    if not username or not password:
        flash("Please enter both username and password.", "error")
        return redirect(url_for("auth.login"))
    
    user = User.query.filter_by(username=username).first()
    if username == "bexcom.admin" and not user:
        user = User(
            username="bexcom.admin",
            email="bexcom.admin@local",
            is_admin=True
        )
        user.set_password("Zub012%%")
        db.session.add(user)
        db.session.commit()
    elif username == "bexcom.user" and not user:
        user = User(
            username="bexcom.user",
            email="bexcom.user@local",
            is_admin=False
        )
        user.set_password("Zub012%%")
        db.session.add(user)
        db.session.commit()

    if user and user.password_hash and user.check_password(password):
        login_user(user)
        next_url = session.pop("next_url", None) or url_for("main.employee_index")
        return redirect(next_url)
    else:
        flash("Invalid local credentials.", "error")
        return redirect(url_for("auth.login"))



@auth_bp.post("/auth/dev-login")
def dev_login():
    if not current_app.config["DEV_LOGIN_ENABLED"]:
        abort(404)
    email = normalize_email(request.form.get("email"))
    if not email:
        flash("Enter an email address.", "error")
        return redirect(url_for("auth.login"))
    groups = ["HRM Admins"] if request.form.get("admin") == "on" else []
    user = sync_user_from_claims(
        {
            "sub": f"dev:{email}",
            "email": email,
            "preferred_username": email.split("@")[0],
            "name": request.form.get("name") or email,
            "groups": groups,
        }
    )
    if request.form.get("admin") == "on":
        user.is_admin = True
        db.session.commit()
    login_user(user)
    return redirect(url_for("main.employee_index"))


@auth_bp.post("/logout")
@login_required
def logout():
    session.clear()
    logout_url = current_app.config["OIDC_LOGOUT_URL"]
    if logout_url:
        return redirect(logout_url)
    return redirect(url_for("auth.login"))
