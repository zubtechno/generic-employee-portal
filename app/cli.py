import json
from pathlib import Path

import click
from flask import current_app

from .importer import copy_imported_photos, parse_hrm_html, write_seed_json
from .models import AuditLog, Employee, db
from .utils import normalize_email


def upsert_employee(item):
    employee = Employee.query.filter_by(employee_id=item["employee_id"]).one_or_none()
    if employee is None:
        employee = Employee(employee_id=item["employee_id"])
        db.session.add(employee)

    employee.full_name = item.get("full_name") or employee.full_name or "Unnamed Employee"
    employee.preferred_name = item.get("preferred_name") or None
    employee.email = normalize_email(item.get("email"))
    employee.phone = item.get("phone") or None
    employee.extension = item.get("extension") or None
    employee.department = item.get("department") or None
    employee.designation = item.get("designation") or None
    employee.blood_group = item.get("blood_group") or None
    employee.fun_fact = item.get("fun_fact") or None
    employee.photo_path = item.get("photo_path") or employee.photo_path
    employee.is_active = bool(item.get("is_active", True))
    employee.serial_no = int(item.get("serial_no", 999))
    return employee


def seed_departments():
    from .models import Department
    if Department.query.first():
        return
        
    default_structure = [
        {
            "name": "Sales & Distribution",
            "serial_no": 1,
            "subs": [
                {"name": "Direct Sales", "serial_no": 1},
                {"name": "Distribution", "serial_no": 2},
                {"name": "Circle Sales", "serial_no": 3}
            ]
        },
        {
            "name": "Marketing & Platform Services",
            "serial_no": 2,
            "subs": [
                {"name": "Marketing Communications", "serial_no": 1},
                {"name": "Strategic Marketing", "serial_no": 2},
                {"name": "Platform Services", "serial_no": 3},
                {"name": "Product", "serial_no": 4}
            ]
        },
        {
            "name": "Customer Operations",
            "serial_no": 3,
            "subs": []
        },
        {
            "name": "Accounts & Finance",
            "serial_no": 4,
            "subs": [
                {"name": "Accounts", "serial_no": 1},
                {"name": "Finance", "serial_no": 2},
                {"name": "Supply Chain Management", "serial_no": 3}
            ]
        },
        {
            "name": "Administration",
            "serial_no": 5,
            "subs": []
        },
        {
            "name": "Technology",
            "serial_no": 6,
            "subs": [
                {"name": "Video Network", "serial_no": 1},
                {"name": "Network & Infra", "serial_no": 2},
                {"name": "Enterprise Systems", "serial_no": 3},
                {"name": "Digital Solutions & Engineering", "serial_no": 4}
            ]
        },
        {
            "name": "Human Resources",
            "serial_no": 7,
            "subs": []
        },
        {
            "name": "Regulatory & Legal Affairs",
            "serial_no": 8,
            "subs": [
                {"name": "Regulatory Affairs", "serial_no": 1},
                {"name": "Anti-piracy Operations", "serial_no": 2},
                {"name": "Legal Affairs", "serial_no": 3}
            ]
        }
    ]
    
    for main_info in default_structure:
        main_dept = Department(name=main_info["name"], serial_no=main_info["serial_no"])
        db.session.add(main_dept)
        db.session.flush()
        
        for sub_info in main_info["subs"]:
            sub_dept = Department(
                name=sub_info["name"],
                parent_id=main_dept.id,
                serial_no=sub_info["serial_no"]
            )
            db.session.add(sub_dept)
            
    db.session.commit()


def seed_settings():
    from .models import Setting
    defaults = {
        "app_name": "Employee Portal",
        "logo_path": "img/logo.png",
        "services_page_enabled": "1",
        "services_page_visibility": "all",  # "all" or "admin"
    }
    for key, value in defaults.items():
        if not Setting.query.filter_by(key=key).first():
            db.session.add(Setting(key=key, value=value))
    db.session.commit()


def seed_services():
    from .models import ServiceLink
    if ServiceLink.query.first():
        return
    services = [
        # Sales & Lead Management
        {"name": "Lead", "url": "http://akashdth.com", "category": "Sales & Lead Management", "managing_team": "Sales Operations", "contact_person": "Md. Moshiur Rahman", "sort_order": 1},
        {"name": "Bulk Lead", "url": "http://182.163.100", "category": "Sales & Lead Management", "managing_team": "Sales Operations", "contact_person": "Md. Abu Sayeed Ashraful Kamal", "sort_order": 2},
        {"name": "Emp Lead Portal", "url": "http://akashdth.com", "category": "Sales & Lead Management", "managing_team": "Sales Operations / HR", "contact_person": "Samiha Khan", "sort_order": 3},
        {"name": "Online Sales", "url": "http://182.163.100", "category": "Sales & Lead Management", "managing_team": "Digital Sales Team", "contact_person": "Muhammad Saqib Hussain", "sort_order": 4},
        # ERP & Finance
        {"name": "ERP (Silverlight)", "url": "http://akashdth.com", "category": "ERP & Finance", "managing_team": "ERP Core Team", "contact_person": "Md. Mahbub Hasan FCA", "sort_order": 5},
        {"name": "ERP (Angular)", "url": "http://akashdth.com", "category": "ERP & Finance", "managing_team": "ERP Core Team", "contact_person": "Md. Mahbub Hasan FCA", "sort_order": 6},
        {"name": "Billing", "url": "http://akashdth.com", "category": "ERP & Finance", "managing_team": "Finance Operations", "contact_person": "A.K.M Javed Mansur", "sort_order": 7},
        {"name": "FR Mgt", "url": "http://182.163.100.236:8052", "category": "ERP & Finance", "managing_team": "Finance Operations", "contact_person": "Selim Hossain", "sort_order": 8},
        {"name": "CMS", "url": "http://akashdth.com", "category": "ERP & Finance", "managing_team": "Content & Commercial Ops", "contact_person": "Mohammad Kaikobad Shaikh", "sort_order": 9},
        # Business Intelligence
        {"name": "Reporting Server", "url": "http://akashdth.com", "category": "Business Intelligence (BI)", "managing_team": "BI & Analytics", "contact_person": "Shamima Nasrin", "sort_order": 10},
        {"name": "AKASH Dashboard", "url": "http://akashdth.com", "category": "Business Intelligence (BI)", "managing_team": "BI & Analytics", "contact_person": "Shamima Nasrin", "sort_order": 11},
        # HR & Admin
        {"name": "HRIS", "url": "https://akashdth.com", "category": "Human Resources & Admin", "managing_team": "Human Resources (HR)", "contact_person": "Samiha Khan", "sort_order": 12},
        {"name": "Bexcom Contact Details", "url": "https://bexcom.net", "category": "Human Resources & Admin", "managing_team": "Human Resources (HR)", "contact_person": "Sikder Md. Firoz Samad", "sort_order": 13},
        {"name": "Document Scan Site", "url": "https://sharepoint.com", "category": "Human Resources & Admin", "managing_team": "Central Operations", "contact_person": "Md. Masum Shaikh", "sort_order": 14},
        # Core Operations
        {"name": "Info Bank", "url": "http://akashdth.com", "category": "Core Operations & Support", "managing_team": "Knowledge Management", "contact_person": "Khondoker Md. Foysal Arif", "sort_order": 15},
        {"name": "360", "url": "http://182.163.100", "category": "Core Operations & Support", "managing_team": "Call Center Operations", "contact_person": "Md. Abu Rasel", "sort_order": 16},
        {"name": "AKASH App", "url": "http://akashdth.com", "category": "Core Operations & Support", "managing_team": "Product & Tech Team", "contact_person": "Ashraful Haque", "sort_order": 17},
        {"name": "QA Portal", "url": "http://akashdth.com", "category": "Core Operations & Support", "managing_team": "Quality Assurance (QA)", "contact_person": "Asraful Islam", "sort_order": 18},
        {"name": "Admin Portal", "url": "http://akashdth.com", "category": "Core Operations & Support", "managing_team": "IT System Admin", "contact_person": "Khondoker Md. Foysal Arif", "sort_order": 19},
        {"name": "FSM", "url": "https://akashdth.com", "category": "Core Operations & Support", "managing_team": "Field Service Management", "contact_person": "Md. Abdul Hannan", "sort_order": 20},
        {"name": "SMBS", "url": "https://10.16.105", "category": "Core Operations & Support", "managing_team": "CRM Team", "contact_person": "Mishkat Zaman Atonu", "sort_order": 21},
    ]
    for s in services:
        db.session.add(ServiceLink(**s))
    db.session.commit()
    click.echo(f"Seeded {len(services)} service links.")


def _ensure_clearance_tables():
    """Create clearance tables if they do not exist yet (safe on existing DBs)."""
    from sqlalchemy import text
    try:
        db.create_all()
    except Exception as e:
        click.echo(f"Clearance table ensure warning: {e}")


def _process_clearance_reminders():
    """Send reminder notifications to pending clearance approvers at defined day thresholds."""
    from datetime import date
    from .models import (
        ClearanceRequest, ClearanceApproval, Notification,
        CLEARANCE_REMINDER_DAYS
    )
    today = date.today()
    active_requests = ClearanceRequest.query.filter(
        ClearanceRequest.status.in_(['pending', 'in_progress'])
    ).all()
    for req in active_requests:
        days_elapsed = (today - req.created_at.date()).days
        for approval in req.approvals:
            if approval.status != 'pending':
                continue
            reminded = approval.days_reminded
            for threshold in CLEARANCE_REMINDER_DAYS:
                if days_elapsed >= threshold and threshold not in reminded:
                    # Create reminder notification
                    db.session.add(Notification(
                        user_id=approval.approver_user_id,
                        message=(
                            f"⏰ Reminder (Day {threshold}): Clearance {req.request_no} for "
                            f"{req.employee.full_name} is awaiting your approval."
                        ),
                    ))
                    approval.mark_reminded(threshold)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def _process_clearance_deactivations():
    """Auto-deactivate employees whose clearance is fully cleared and LWD has passed."""
    from datetime import date
    from .models import ClearanceRequest, AuditLog
    today = date.today()
    cleared_requests = ClearanceRequest.query.filter(
        ClearanceRequest.status == 'cleared'
    ).all()
    for req in cleared_requests:
        if req.last_working_date <= today and req.employee.is_active:
            req.employee.is_active = False
            db.session.add(AuditLog(
                actor_email='system',
                action='auto_deactivate_employee',
                target_employee_id=req.employee.employee_id,
                details=(
                    f"Auto-deactivated via clearance {req.request_no}. "
                    f"Last working date: {req.last_working_date}"
                )
            ))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def _process_expiration_reminders_background():
    """Send expiration alerts to Admins/Super Admins and matched owners at 60, 45, 30 days thresholds."""
    from datetime import date
    from .models import ExpirationReminder, ExpirationReminderLog, Notification, Setting, User
    
    # Fetch reminder days configuration
    try:
        days_cfg = Setting.query.get("reminder_days_config")
        thresholds = [int(x.strip()) for x in days_cfg.value.split(",")] if days_cfg else [60, 45, 30]
    except Exception:
        thresholds = [60, 45, 30]
        
    today = date.today()
    reminders = ExpirationReminder.query.all()
    
    for r in reminders:
        days_left = (r.expiry_date - today).days
        if days_left < 0:
            continue # Already expired
            
        for th in thresholds:
            if days_left <= th:
                # Check if notification was already sent for this reminder at this threshold
                already_notified = ExpirationReminderLog.query.filter_by(
                    reminder_id=r.id, threshold_days=th
                ).first()
                
                if not already_notified:
                    msg = f"⏳ Expiry Warning: The item '{r.license_name}' ({r.category.name if r.category else 'Other'}) expires in {days_left} days (on {r.expiry_date.strftime('%Y-%m-%d')})."
                    
                    # Notify Super Admins and Reminder Admins
                    recipient_users = User.query.filter(
                        (User.is_admin == True) | (User.is_reminder_admin == True)
                    ).all()
                    
                    recipients = {u.id for u in recipient_users}
                    
                    # Notify matched System Owner (name or email matches)
                    if r.system_owner:
                        owner_val = r.system_owner.strip().lower()
                        matched_owner = User.query.filter(
                            (db.func.lower(User.email) == owner_val) | 
                            (db.func.lower(User.full_name) == owner_val) |
                            (db.func.lower(User.username) == owner_val)
                        ).first()
                        if matched_owner:
                            recipients.add(matched_owner.id)
                            
                    for r_id in recipients:
                        db.session.add(Notification(user_id=r_id, message=msg))
                        
                    db.session.add(ExpirationReminderLog(reminder_id=r.id, threshold_days=th))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Initialize the database and seed it if empty."""
        try:
            inspector = db.inspect(db.engine)
            rebuild = False
            if "user" in inspector.get_table_names():
                user_cols = [c["name"] for c in inspector.get_columns("user")]
                if "password_hash" not in user_cols:
                    rebuild = True
                else:
                    from sqlalchemy import text
                    for col in ["is_directory_admin", "is_service_admin", "is_support_admin", "is_audit_admin", "is_clearance_admin", "is_reminder_admin", "is_reminder_viewer"]:
                        if col not in user_cols:
                            click.echo(f"Adding column '{col}' to user table...")
                            try:
                                with db.engine.begin() as conn:
                                    conn.execute(text(f"ALTER TABLE user ADD COLUMN {col} BOOLEAN NOT NULL DEFAULT 0"))
                            except Exception as alter_err:
                                click.echo(f"Column addition failed: {alter_err}")
            if "employee" in inspector.get_table_names():
                # Check Notification columns for clearance_request_id
                if "notification" in inspector.get_table_names():
                    notif_cols = [c["name"] for c in inspector.get_columns("notification")]
                    if "clearance_request_id" not in notif_cols:
                        click.echo("Adding column 'clearance_request_id' to notification table...")
                        try:
                            with db.engine.begin() as conn:
                                conn.execute(text("ALTER TABLE notification ADD COLUMN clearance_request_id INTEGER REFERENCES clearance_request(id)"))
                        except Exception as alter_err:
                            click.echo(f"Notification column migration warning: {alter_err}")
                emp_cols = [c["name"] for c in inspector.get_columns("employee")]
                if "serial_no" not in emp_cols or "location" in emp_cols:
                    rebuild = True
                else:
                    # Force rebuild if all serials are the broken default 999
                    from sqlalchemy import text
                    with db.engine.connect() as conn:
                        result = conn.execute(text(
                            "SELECT COUNT(*) FROM employee WHERE serial_no != 999"
                        ))
                        non_default_count = result.scalar()
                    if non_default_count == 0 and Employee.query.count() > 0:
                        click.echo("All serials are default (999). Forcing reseed...")
                        rebuild = True
            if "department" not in inspector.get_table_names():
                rebuild = True
            if "setting" not in inspector.get_table_names():
                rebuild = True
            if "service_link" in inspector.get_table_names():
                svc_cols = [c["name"] for c in inspector.get_columns("service_link")]
                if "contact_person" not in svc_cols:
                    click.echo("Outdated service_link table detected. Dropping it...")
                    from .models import ServiceLink
                    try:
                        ServiceLink.__table__.drop(db.engine)
                    except Exception as drop_err:
                        click.echo(f"Drop failed, drop table raw command: {drop_err}")
            if rebuild:
                click.echo("Outdated schema detected. Rebuilding database...")
                db.drop_all()
        except Exception as e:
            click.echo(f"Warning: schema inspection failed: {e}")

        db.create_all()
        seed_departments()
        seed_settings()
        seed_services()
        # Ensure clearance tables exist (safe no-op if already present)
        _ensure_clearance_tables()
        # Process any overdue clearance reminders and auto-deactivations or reminders
        try:
            _process_clearance_reminders()
            _process_clearance_deactivations()
            # Inline function call to process expiration reminders
            _process_expiration_reminders_background()
        except Exception as ce:
            click.echo(f"Clearance/reminders background tasks warning: {ce}")
        if current_app.config["AUTO_SEED"]:
            from .seed import seed_if_empty
            seed_if_empty(current_app)
        click.echo("Database initialized and seeded.")

    @app.cli.command("update-serials")
    def update_serials():
        """Re-apply serial_no values from seed JSON without dropping the database."""
        seed_path = Path(current_app.config["SEED_JSON_PATH"])
        if not seed_path.exists():
            click.echo(f"Seed file not found: {seed_path}")
            return

        payload = json.loads(seed_path.read_text(encoding="utf-8"))
        updated = 0
        skipped = 0
        for item in payload.get("employees", []):
            emp_id = str(item.get("employee_id", "")).strip()
            serial = item.get("serial_no")
            if not emp_id or serial is None:
                skipped += 1
                continue
            employee = Employee.query.filter_by(employee_id=emp_id).one_or_none()
            if employee:
                employee.serial_no = int(serial)
                updated += 1
            else:
                skipped += 1
        db.session.commit()
        click.echo(f"Updated serial_no for {updated} employees. Skipped {skipped}.")

    @app.cli.command("import-hrm")
    @click.option("--html", "html_path", required=True, type=click.Path(exists=True))
    @click.option("--assets", "assets_path", type=click.Path(exists=True))
    @click.option("--copy-photos/--no-copy-photos", default=True)
    @click.option("--write-seed", "seed_path", type=click.Path())
    def import_hrm(html_path, assets_path, copy_photos, seed_path):
        """Import employees from the saved hrm.bexcom.net HTML export."""
        employees = parse_hrm_html(html_path)
        copied = 0
        if copy_photos and assets_path:
            destination = Path(current_app.config["UPLOAD_FOLDER"]) / "imported"
            copied = copy_imported_photos(employees, assets_path, destination)

        for item in employees:
            upsert_employee(item)
        db.session.add(
            AuditLog(
                actor_email="cli",
                action="import",
                details=f"Imported {len(employees)} employees from {html_path}",
            )
        )
        db.session.commit()

        if seed_path:
            write_seed_json(employees, seed_path)

        click.echo(f"Imported {len(employees)} employees, copied {copied} photos")

