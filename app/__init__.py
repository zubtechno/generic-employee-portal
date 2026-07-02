import os
from pathlib import Path

from flask import Flask, g
from werkzeug.middleware.proxy_fix import ProxyFix

from .auth import auth_bp, init_oauth, load_current_user
from .cli import register_cli
from .config import Config
from .models import db
from .routes import main_bp
from .security import csrf_field, csrf_token, protect_csrf


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config.from_prefixed_env()

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["PROFILE_UPLOAD_SUBDIR"]).mkdir(parents=True, exist_ok=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    if app.config["TRUST_PROXY"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    init_oauth(app)

    app.before_request(load_current_user)
    app.before_request(protect_csrf)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    register_cli(app)

    @app.context_processor
    def inject_context():
        from .models import Setting
        try:
            settings_rows = Setting.query.all()
            app_settings = {s.key: s.value for s in settings_rows}
            app_name = app_settings.get("app_name", "Employee Portal")
            logo_path = app_settings.get("logo_path", "img/logo.png")
        except Exception:
            app_settings = {}
            app_name = "Employee Portal"
            logo_path = "img/logo.png"
            
        unread_notifications_count = 0
        clearance_nav_visible = False
        reminder_nav_visible = False
        if getattr(g, "current_user", None):
            try:
                from .models import Notification
                unread_notifications_count = Notification.query.filter_by(
                    user_id=g.current_user.id, is_read=False
                ).count()
            except Exception:
                pass
            try:
                from .models import ClearanceInitiator, ClearanceApproverConfig
                user = g.current_user
                if (user.is_admin or
                        ClearanceInitiator.query.filter_by(user_id=user.id).first() or
                        ClearanceApproverConfig.query.filter_by(user_id=user.id).first()):
                    clearance_nav_visible = True
            except Exception:
                pass
            try:
                user = g.current_user
                if (user.is_admin or 
                        getattr(user, "is_reminder_admin", False) or 
                        getattr(user, "is_reminder_viewer", False)):
                    reminder_nav_visible = True
            except Exception:
                pass

        from datetime import datetime as _dt
        import pytz
        
        def local_time(dt):
            if not dt:
                return ""
            # If datetime has timezone info (is timezone-aware)
            if dt.tzinfo is not None:
                local_dt = dt.astimezone(pytz.timezone('Asia/Dhaka'))
            else:
                # Fallback assuming database stores UTC datetimes
                utc_dt = pytz.utc.localize(dt)
                local_dt = utc_dt.astimezone(pytz.timezone('Asia/Dhaka'))
            return local_dt

        return {
            "current_user": getattr(g, "current_user", None),
            "csrf_token": csrf_token,
            "csrf_field": csrf_field,
            "company_name": app.config["COMPANY_NAME"],
            "app_name": app_name,
            "logo_path": logo_path,
            "app_settings": app_settings,
            "unread_notifications_count": unread_notifications_count,
            "clearance_nav_visible": clearance_nav_visible,
            "reminder_nav_visible": reminder_nav_visible,
            "now": _dt.now(pytz.timezone('Asia/Dhaka')),
            "local_time": local_time,
        }

    return app

