import json
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc)


from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    authentik_sub = db.Column(db.String(255), unique=True, nullable=True, index=True)
    email = db.Column(db.String(255), unique=True, nullable=True, index=True)
    username = db.Column(db.String(255), nullable=True)
    full_name = db.Column(db.String(255), nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    groups_json = db.Column(db.Text, nullable=False, default="[]")
    employee_id = db.Column(db.String(64), nullable=True, index=True)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    is_directory_admin = db.Column(db.Boolean, nullable=False, default=False)
    is_service_admin = db.Column(db.Boolean, nullable=False, default=False)
    is_support_admin = db.Column(db.Boolean, nullable=False, default=False)
    is_audit_admin = db.Column(db.Boolean, nullable=False, default=False)
    is_clearance_admin = db.Column(db.Boolean, nullable=False, default=False)
    is_reminder_admin = db.Column(db.Boolean, nullable=False, default=False)
    is_reminder_viewer = db.Column(db.Boolean, nullable=False, default=False)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    @property
    def is_any_admin(self):
        return (
            self.is_admin or
            self.is_directory_admin or
            self.is_service_admin or
            self.is_support_admin or
            self.is_audit_admin or
            self.is_clearance_admin or
            self.is_reminder_admin or
            self.is_reminder_viewer
        )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def groups(self):
        try:
            return json.loads(self.groups_json or "[]")
        except json.JSONDecodeError:
            return []

    @property
    def display_name(self):
        return self.full_name or self.username or self.email



class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    serial_no = db.Column(db.Integer, nullable=False, default=999)
    full_name = db.Column(db.String(255), nullable=False, index=True)
    preferred_name = db.Column(db.String(255), nullable=True, index=True)
    email = db.Column(db.String(255), nullable=True, unique=True, index=True)
    phone = db.Column(db.String(64), nullable=True)
    extension = db.Column(db.String(64), nullable=True)
    department = db.Column(db.String(255), nullable=True, index=True)
    designation = db.Column(db.String(255), nullable=True, index=True)
    blood_group = db.Column(db.String(32), nullable=True)
    fun_fact = db.Column(db.Text, nullable=True)
    photo_path = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    @property
    def display_name(self):
        return self.preferred_name or self.full_name

    @property
    def initials(self):
        words = [part for part in self.full_name.replace(".", " ").split() if part]
        return "".join(word[0].upper() for word in words[:2]) or "AK"

    def vcard_data(self):
        import urllib.parse
        fn = self.full_name or "Unnamed"
        org = "AKASH Digital TV"
        title = self.designation or ""
        email = self.email or ""
        phone = self.phone or ""
        pabx = self.extension or ""
        
        vcard_lines = [
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"FN:{fn}",
            f"ORG:{org}",
            f"TITLE:{title}",
            f"TEL;TYPE=CELL:{phone}",
        ]
        if pabx:
            vcard_lines.append(f"TEL;TYPE=WORK,VOICE:{pabx}")
        if email:
            vcard_lines.append(f"EMAIL;TYPE=PREF,INTERNET:{email}")
        vcard_lines.append("END:VCARD")
        
        vcard_text = "\r\n".join(vcard_lines)
        return urllib.parse.quote(vcard_text)


class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=True)
    serial_no = db.Column(db.Integer, nullable=False, default=999)
    
    sub_departments = db.relationship(
        'Department',
        backref=db.backref('parent', remote_side=[id]),
        cascade='all, delete-orphan',
        order_by='Department.serial_no'
    )


class Setting(db.Model):
    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text, nullable=True)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_email = db.Column(db.String(255), nullable=True, index=True)
    action = db.Column(db.String(64), nullable=False, index=True)
    target_employee_id = db.Column(db.String(64), nullable=True, index=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class ServiceLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False, index=True)
    url = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(255), nullable=False, index=True)
    managing_team = db.Column(db.String(255), nullable=True)
    contact_person = db.Column(db.String(255), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=999)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_no = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    category = db.Column(db.String(255), nullable=False, index=True)
    subject = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(32), nullable=False, default="Normal", index=True)
    status = db.Column(db.String(32), nullable=False, default="Open", index=True)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    attachment_path = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    # Relationships
    reporter = db.relationship("User", foreign_keys=[user_id], backref="tickets_reported")
    assignee = db.relationship("User", foreign_keys=[assigned_to_id], backref="tickets_assigned")
    comments = db.relationship("TicketComment", backref="ticket", cascade="all, delete-orphan", order_by="TicketComment.created_at")


class TicketComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("ticket.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    attachment_path = db.Column(db.String(500), nullable=True)
    is_internal = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    # Relationships
    author = db.relationship("User")


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("ticket.id"), nullable=True)
    clearance_request_id = db.Column(db.Integer, db.ForeignKey("clearance_request.id"), nullable=True)
    message = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    # Relationships
    user = db.relationship("User", backref="notifications_received")
    ticket = db.relationship("Ticket")
    clearance_request = db.relationship("ClearanceRequest")


# ─────────────────────────────────────────────────────────────────────────────
# Email Event Hooks for Portal Notifications
# ─────────────────────────────────────────────────────────────────────────────
from sqlalchemy import event

@event.listens_for(Notification, 'after_insert')
def receive_after_insert(mapper, connection, target):
    """Fires automatically after any Notification record is inserted in the DB."""
    from .utils import send_email
    from .models import User
    
    # We query the DB for the target user's email since target.user might not be loaded yet
    try:
        # Fetch user's email directly using connection to avoid session re-entry issues
        result = connection.execute(
            db.select(User.email, User.full_name).where(User.id == target.user_id)
        ).first()
        
        if result and result[0]:
            user_email = result[0]
            display_name = result[1] or "User"
            from flask import current_app
            subject = f"Portal Notification Alert: {current_app.config.get('PORTAL_NAME', 'HRM Portal')}"
            body = (
                f"Hello {display_name},\n\n"
                f"You have received a new notification on the HRM Portal:\n\n"
                f"\"{target.message}\"\n\n"
                f"Please log in to the portal to view details.\n\n"
                f"Best regards,\n"
                f"Employee Portal"
            )
            # Send the email in a try-except to prevent connection/network blocks from rolling back database operations
            try:
                # Need current app context to retrieve mail config
                send_email(user_email, subject, body)
            except Exception:
                pass
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Technology Clearance Flow Models
# ─────────────────────────────────────────────────────────────────────────────

CLEARANCE_REMINDER_DAYS = [1, 3, 7, 15, 20, 25, 30]


class ClearanceInitiator(db.Model):
    """Users allowed to submit clearance requests (configured by clearance admin)."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    added_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    user = db.relationship('User', foreign_keys=[user_id], backref='clearance_initiator_entry')
    added_by = db.relationship('User', foreign_keys=[added_by_id])


class ClearanceApproverConfig(db.Model):
    """Users configured as clearance approvers (set by clearance admin)."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    label = db.Column(db.String(255), nullable=True)   # e.g. "IT Head", "HR Manager"
    sort_order = db.Column(db.Integer, nullable=False, default=999)
    added_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    user = db.relationship('User', foreign_keys=[user_id], backref='clearance_approver_entry')
    added_by = db.relationship('User', foreign_keys=[added_by_id])


class ClearanceRequest(db.Model):
    """A clearance request for a departing employee."""
    id = db.Column(db.Integer, primary_key=True)
    request_no = db.Column(db.String(32), unique=True, nullable=False, index=True)  # CLR-YYYYMMDD-XXXX
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    initiated_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    last_working_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(32), nullable=False, default='pending', index=True)
    # status: 'pending' | 'in_progress' | 'cleared' | 'cancelled'
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    employee = db.relationship('Employee', backref='clearance_requests')
    initiated_by = db.relationship('User', foreign_keys=[initiated_by_id], backref='clearances_initiated')
    approvals = db.relationship(
        'ClearanceApproval',
        backref='request',
        cascade='all, delete-orphan',
        order_by='ClearanceApproval.sort_order'
    )

    @property
    def pending_approvals(self):
        return [a for a in self.approvals if a.status == 'pending']

    @property
    def cleared_approvals(self):
        return [a for a in self.approvals if a.status == 'cleared']

    @property
    def all_cleared(self):
        return bool(self.approvals) and all(a.status == 'cleared' for a in self.approvals)


class ClearanceApproval(db.Model):
    """One approval slot per approver per clearance request."""
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('clearance_request.id'), nullable=False)
    approver_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    label = db.Column(db.String(255), nullable=True)   # Copied from config at request time
    comment = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(32), nullable=False, default='pending', index=True)
    # status: 'pending' | 'cleared'
    cleared_at = db.Column(db.DateTime(timezone=True), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=999)
    days_reminded_json = db.Column(db.Text, nullable=False, default='[]')  # JSON list of reminder days sent

    approver = db.relationship('User', foreign_keys=[approver_user_id], backref='clearance_approvals')

    @property
    def days_reminded(self):
        try:
            return json.loads(self.days_reminded_json or '[]')
        except Exception:
            return []

    def mark_reminded(self, day):
        reminded = self.days_reminded
        if day not in reminded:
            reminded.append(day)
            self.days_reminded_json = json.dumps(reminded)


# ─────────────────────────────────────────────────────────────────────────────
# Expiration Reminder Models
# ─────────────────────────────────────────────────────────────────────────────

class ExpirationReminderCategory(db.Model):
    """Custom categories for reminder item type dropdown (e.g. Domain Name Renewal, SSL, etc.)"""
    __tablename__ = "expiration_reminder_category"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class ExpirationReminder(db.Model):
    """Saves reminder parameters for licenses, domains, certificates, etc."""
    __tablename__ = "expiration_reminder"
    id = db.Column(db.Integer, primary_key=True)
    license_name = db.Column(db.String(255), nullable=False, index=True)
    stored_location = db.Column(db.String(500), nullable=True)
    system_app_used = db.Column(db.String(500), nullable=True)
    system_owner = db.Column(db.String(255), nullable=True, index=True) # Text name/email of owner
    vendor_info = db.Column(db.Text, nullable=True)
    expiry_date = db.Column(db.Date, nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('expiration_reminder_category.id'), nullable=True)
    path_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    category = db.relationship('ExpirationReminderCategory', backref='reminders')

    @property
    def status(self):
        from datetime import date
        today = date.today()
        days_left = (self.expiry_date - today).days
        if days_left < 0:
            return "expired"
        elif days_left <= 30:
            return "critical"
        elif days_left <= 60:
            return "warning"
        return "ok"


class ExpirationReminderLog(db.Model):
    """Keeps track of sent expiry notification records to avoid duplicates."""
    __tablename__ = "expiration_reminder_log"
    id = db.Column(db.Integer, primary_key=True)
    reminder_id = db.Column(db.Integer, db.ForeignKey('expiration_reminder.id', ondelete='CASCADE'), nullable=False)
    threshold_days = db.Column(db.Integer, nullable=False) # e.g. 60, 45, 30, 0
    notified_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
