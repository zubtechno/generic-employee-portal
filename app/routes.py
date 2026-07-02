from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .auth import (
    admin_required,
    login_required,
    directory_admin_required,
    service_admin_required,
    support_admin_required,
    audit_admin_required,
    clearance_admin_required,
    reminder_admin_required,
    reminder_viewer_required,
)
from .models import AuditLog, Employee, db
from .utils import normalize_email, photo_static_path, save_employee_photo


main_bp = Blueprint("main", __name__)


EMPLOYEE_FIELDS = [
    "employee_id",
    "serial_no",
    "full_name",
    "preferred_name",
    "email",
    "phone",
    "extension",
    "department",
    "designation",
    "blood_group",
    "fun_fact",
]


@main_bp.app_template_filter("photo_path")
def photo_path_filter(employee):
    return photo_static_path(employee)


def can_update_photo(employee):
    user = g.current_user
    if not user:
        return False
    if user.is_admin:
        return True
    if user.employee_id and user.employee_id == employee.employee_id:
        return True
    return bool(user.email and employee.email and user.email.lower() == employee.email.lower())


def departments_with_counts():
    rows = (
        db.session.query(Employee.department, func.count(Employee.id))
        .filter(Employee.is_active.is_(True))
        .group_by(Employee.department)
        .order_by(Employee.department)
        .all()
    )
    return [(department or "Unassigned", count) for department, count in rows]


def employee_from_form(employee):
    for field in EMPLOYEE_FIELDS:
        value = request.form.get(field, "").strip()
        if field == "email":
            value = normalize_email(value)
        elif field == "serial_no":
            try:
                value = int(value) if value else 999
            except ValueError:
                value = 999
        setattr(employee, field, value if value is not None else None)
    employee.is_active = request.form.get("is_active") == "on"
    return employee


def log_action(action, employee=None, details=None):
    db.session.add(
        AuditLog(
            actor_email=g.current_user.email if g.current_user else None,
            action=action,
            target_employee_id=employee.employee_id if employee else None,
            details=details,
        )
    )


@main_bp.get("/")
def home():
    if not getattr(g, "current_user", None):
        return redirect(url_for("auth.login"))
    return redirect(url_for("main.employee_index"))


@main_bp.get("/employees")
@login_required
def employee_index():
    from .models import Department
    main_depts = Department.query.filter_by(parent_id=None).order_by(Department.serial_no).all()
    DEPARTMENT_STRUCTURE = [
        {
            "name": md.name,
            "subs": [sub.name for sub in md.sub_departments]
        }
        for md in main_depts
    ]

    query_text = request.args.get("q", "").strip()
    department = request.args.get("department", "").strip()
    include_inactive = request.args.get("inactive") == "1" and g.current_user.is_admin
    
    view_mode = request.args.get("view", session.get("view_mode", "list"))
    session["view_mode"] = view_mode

    query = Employee.query
    if not include_inactive:
        query = query.filter(Employee.is_active.is_(True))

    # Find the department in our structure to handle main-to-sub mapping
    target_dept = None
    for d in DEPARTMENT_STRUCTURE:
        if d["name"] == department:
            target_dept = d
            break

    if department:
        if target_dept and target_dept["subs"]:
            allowed_depts = [department] + target_dept["subs"]
            query = query.filter(Employee.department.in_(allowed_depts))
        else:
            query = query.filter(Employee.department == department)

    if query_text:
        like = f"%{query_text}%"
        query = query.filter(
            or_(
                Employee.full_name.ilike(like),
                Employee.preferred_name.ilike(like),
                Employee.email.ilike(like),
                Employee.phone.ilike(like),
                Employee.extension.ilike(like),
                Employee.employee_id.ilike(like),
                Employee.department.ilike(like),
                Employee.designation.ilike(like),
                Employee.blood_group.ilike(like),
            )
        )

    employees = query.order_by(Employee.department, Employee.serial_no, Employee.full_name).all()
    total_active = Employee.query.filter(Employee.is_active.is_(True)).count()
    total_inactive = Employee.query.filter(Employee.is_active.is_(False)).count()

    # Fetch active counts for each department from DB
    counts_query = (
        db.session.query(Employee.department, func.count(Employee.id))
        .filter(Employee.is_active.is_(True))
        .group_by(Employee.department)
        .all()
    )
    raw_counts = {dept: count for dept, count in counts_query if dept}

    # Build hierarchical list
    known_depts = set()
    hierarchical_departments = []
    for d in DEPARTMENT_STRUCTURE:
        main_name = d["name"]
        known_depts.add(main_name)
        main_own_count = raw_counts.get(main_name, 0)
        
        subs_list = []
        main_total_count = main_own_count
        for sub_name in d["subs"]:
            known_depts.add(sub_name)
            sub_count = raw_counts.get(sub_name, 0)
            main_total_count += sub_count
            subs_list.append({
                "name": sub_name,
                "count": sub_count
            })
            
        hierarchical_departments.append({
            "name": main_name,
            "own_count": main_own_count,
            "total_count": main_total_count,
            "subs": subs_list
        })

    # Add any unknown database departments to "Others"
    other_depts = [dept for dept in raw_counts.keys() if dept not in known_depts]
    if other_depts:
        other_subs = []
        other_total = 0
        for dept in other_depts:
            count = raw_counts[dept]
            other_total += count
            other_subs.append({
                "name": dept,
                "count": count
            })
        hierarchical_departments.append({
            "name": "Others",
            "own_count": 0,
            "total_count": other_total,
            "subs": other_subs
        })

    # Group employees by department in the order of DEPARTMENT_STRUCTURE
    ordered_dept_names = []
    for d in DEPARTMENT_STRUCTURE:
        ordered_dept_names.append(d["name"])
        for sub in d["subs"]:
            ordered_dept_names.append(sub)
    ordered_dept_names.append("Others")
    ordered_dept_names.append("Unassigned")

    from collections import defaultdict
    dept_map = defaultdict(list)
    for emp in employees:
        dept = emp.department or "Unassigned"
        if dept not in ordered_dept_names:
            dept_map["Others"].append(emp)
        else:
            dept_map[dept].append(emp)

    grouped_employees = []
    for dept_name in ordered_dept_names:
        dept_emps = dept_map.get(dept_name, [])
        if dept_emps:
            grouped_employees.append({
                "name": dept_name,
                "employees": dept_emps,
                "count": len(dept_emps)
            })

    # Build search hint suggestions for datalist
    blood_groups = ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]
    active_emps = Employee.query.filter(Employee.is_active.is_(True)).with_entities(
        Employee.full_name, Employee.employee_id, Employee.phone, Employee.extension, Employee.blood_group
    ).all()
    search_hints = []
    seen = set()
    for e in active_emps:
        for val in [e.full_name, e.employee_id, e.phone, e.extension, e.blood_group]:
            if val and val.strip() and val not in seen:
                search_hints.append(val.strip())
                seen.add(val.strip())
    for bg in blood_groups:
        if bg not in seen:
            search_hints.append(bg)

    return render_template(
        "employees/index.html",
        employees=employees,
        grouped_employees=grouped_employees,
        hierarchical_departments=hierarchical_departments,
        total_active=total_active,
        total_inactive=total_inactive,
        department=department,
        query_text=query_text,
        include_inactive=include_inactive,
        view_mode=view_mode,
        search_hints=search_hints,
    )


@main_bp.get("/employees/new")
@directory_admin_required
def employee_new():
    from .models import Department
    departments = Department.query.order_by(Department.parent_id, Department.serial_no, Department.name).all()
    return render_template("employees/form.html", employee=Employee(is_active=True), departments=departments, mode="new")


@main_bp.post("/employees/new")
@directory_admin_required
def employee_create():
    employee = employee_from_form(Employee(is_active=True))
    try:
        db.session.add(employee)
        db.session.flush()
        if request.files.get("photo"):
            employee.photo_path = save_employee_photo(request.files["photo"], employee)
        log_action("create", employee)
        db.session.commit()
        flash("Employee created.", "success")
        return redirect(url_for("main.employee_detail", employee_id=employee.employee_id))
    except (IntegrityError, ValueError) as exc:
        db.session.rollback()
        flash(str(getattr(exc, "orig", exc)), "error")
        from .models import Department
        departments = Department.query.order_by(Department.parent_id, Department.serial_no, Department.name).all()
        return render_template("employees/form.html", employee=employee, departments=departments, mode="new"), 400


@main_bp.get("/employees/<employee_id>")
@login_required
def employee_detail(employee_id):
    from .models import Ticket, User
    employee = Employee.query.filter_by(employee_id=employee_id).one_or_none()
    if not employee:
        abort(404)
        
    user = g.current_user
    is_own_profile = False
    if user.employee_id and user.employee_id == employee.employee_id:
        is_own_profile = True
    elif user.email and employee.email and user.email.lower() == employee.email.lower():
        is_own_profile = True
        
    tickets_created = 0
    tickets_closed = 0
    if is_own_profile or user.is_admin:
        # Find User linked to this Employee record
        target_user = None
        if employee.email:
            target_user = User.query.filter(func.lower(User.email) == employee.email.lower()).first()
        if not target_user and employee.employee_id:
            target_user = User.query.filter_by(employee_id=employee.employee_id).first()
            
        if target_user:
            tickets_created = Ticket.query.filter_by(user_id=target_user.id).count()
            tickets_closed = Ticket.query.filter_by(user_id=target_user.id).filter(Ticket.status.in_(["Resolved", "Closed"])).count()

    return render_template(
        "employees/detail.html",
        employee=employee,
        can_update_photo=can_update_photo(employee),
        is_own_profile=is_own_profile,
        tickets_created=tickets_created,
        tickets_closed=tickets_closed
    )


@main_bp.get("/employees/<employee_id>/edit")
@directory_admin_required
def employee_edit(employee_id):
    employee = Employee.query.filter_by(employee_id=employee_id).one_or_none()
    if not employee:
        abort(404)
    from .models import Department
    departments = Department.query.order_by(Department.parent_id, Department.serial_no, Department.name).all()
    return render_template("employees/form.html", employee=employee, departments=departments, mode="edit")


@main_bp.post("/employees/<employee_id>/edit")
@directory_admin_required
def employee_update(employee_id):
    employee = Employee.query.filter_by(employee_id=employee_id).one_or_none()
    if not employee:
        abort(404)
    original_id = employee.employee_id
    employee_from_form(employee)
    try:
        if request.files.get("photo") and request.files["photo"].filename:
            employee.photo_path = save_employee_photo(request.files["photo"], employee)
        log_action("update", employee, details=f"Updated from {original_id}")
        db.session.commit()
        flash("Employee updated.", "success")
        return redirect(url_for("main.employee_detail", employee_id=employee.employee_id))
    except (IntegrityError, ValueError) as exc:
        db.session.rollback()
        flash(str(getattr(exc, "orig", exc)), "error")
        from .models import Department
        departments = Department.query.order_by(Department.parent_id, Department.serial_no, Department.name).all()
        return render_template("employees/form.html", employee=employee, departments=departments, mode="edit"), 400


@main_bp.post("/employees/<employee_id>/delete")
@directory_admin_required
def employee_delete(employee_id):
    from .models import Employee
    employee = Employee.query.filter_by(employee_id=employee_id).one_or_none()
    if not employee:
        abort(404)
    name = employee.full_name
    db.session.delete(employee)
    db.session.commit()
    log_action("delete", employee, details=f"Deleted employee {name}")
    flash(f"Employee '{name}' has been deleted successfully.", "success")
    return redirect(url_for("main.employee_index"))


@main_bp.post("/employees/<employee_id>/photo")
@login_required
def employee_photo(employee_id):
    employee = Employee.query.filter_by(employee_id=employee_id).one_or_none()
    if not employee:
        abort(404)
    if not can_update_photo(employee):
        abort(403)
    try:
        employee.photo_path = save_employee_photo(request.files.get("photo"), employee)
        log_action("photo_update", employee)
        db.session.commit()
        flash("Photo updated.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("main.employee_detail", employee_id=employee.employee_id))


@main_bp.post("/employees/<employee_id>/toggle-active")
@directory_admin_required
def employee_toggle_active(employee_id):
    employee = Employee.query.filter_by(employee_id=employee_id).one_or_none()
    if not employee:
        abort(404)
    employee.is_active = not employee.is_active
    log_action("activate" if employee.is_active else "deactivate", employee)
    db.session.commit()
    flash("Employee status updated.", "success")
    return redirect(url_for("main.employee_detail", employee_id=employee.employee_id))


@main_bp.get("/profile")
@login_required
def profile():
    from .models import Ticket
    employee = None
    if g.current_user.employee_id:
        employee = Employee.query.filter_by(employee_id=g.current_user.employee_id).one_or_none()
    if not employee and g.current_user.email:
        employee = Employee.query.filter(
            func.lower(Employee.email) == g.current_user.email.lower()
        ).one_or_none()
        
    if employee:
        return redirect(url_for("main.employee_detail", employee_id=employee.employee_id))
        
    tickets_created = Ticket.query.filter_by(user_id=g.current_user.id).count()
    tickets_closed = Ticket.query.filter_by(user_id=g.current_user.id).filter(Ticket.status.in_(["Resolved", "Closed"])).count()
    
    return render_template(
        "profile.html",
        employee=employee,
        tickets_created=tickets_created,
        tickets_closed=tickets_closed
    )


@main_bp.get("/admin/audit")
@audit_admin_required
def audit_log():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()
    return render_template("admin/audit.html", logs=logs)


@main_bp.get("/admin/users")
@admin_required
def user_index():
    from .models import User
    users = User.query.order_by(User.username).all()
    return render_template("admin/users.html", users=users)


@main_bp.post("/admin/users/<int:user_id>/save-roles")
@admin_required
def user_save_roles(user_id):
    from .models import User
    if user_id == g.current_user.id:
        flash("You cannot edit your own roles to prevent locking yourself out.", "error")
        return redirect(url_for("main.user_index"))
        
    user = User.query.get_or_404(user_id)
    user.is_admin = request.form.get("is_admin") == "1"
    user.is_directory_admin = request.form.get("is_directory_admin") == "1"
    user.is_service_admin = request.form.get("is_service_admin") == "1"
    user.is_support_admin = request.form.get("is_support_admin") == "1"
    user.is_audit_admin = request.form.get("is_audit_admin") == "1"
    user.is_clearance_admin = request.form.get("is_clearance_admin") == "1"
    user.is_reminder_admin = request.form.get("is_reminder_admin") == "1"
    user.is_reminder_viewer = request.form.get("is_reminder_viewer") == "1"
    db.session.commit()
    
    assigned_roles = []
    if user.is_admin: assigned_roles.append("Super Admin")
    if user.is_directory_admin: assigned_roles.append("Directory Admin")
    if user.is_service_admin: assigned_roles.append("Service Admin")
    if user.is_support_admin: assigned_roles.append("Support Admin")
    if user.is_audit_admin: assigned_roles.append("Audit Admin")
    if user.is_clearance_admin: assigned_roles.append("Clearance Admin")
    if user.is_reminder_admin: assigned_roles.append("Reminder Admin")
    if user.is_reminder_viewer: assigned_roles.append("Reminder Viewer")
    
    log_action("save_roles", details=f"Saved roles for user {user.username}: {', '.join(assigned_roles) or 'None'}")
    flash(f"Roles updated successfully for {user.username}.", "success")
    return redirect(url_for("main.user_index"))


@main_bp.get("/admin/departments")
@directory_admin_required
def department_index():
    from .models import Department
    # Load all main departments (ordered by serial)
    main_depts = Department.query.filter_by(parent_id=None).order_by(Department.serial_no).all()
    # Load all sub-departments for forms
    all_depts = Department.query.order_by(Department.name).all()
    return render_template("admin/departments.html", main_depts=main_depts, all_depts=all_depts)


@main_bp.post("/admin/departments/new")
@directory_admin_required
def department_create():
    from .models import Department
    name = request.form.get("name", "").strip()
    parent_id = request.form.get("parent_id", "").strip()
    serial_no_str = request.form.get("serial_no", "").strip()
    
    if not name:
        flash("Department name is required.", "error")
        return redirect(url_for("main.department_index"))
        
    try:
        serial_no = int(serial_no_str) if serial_no_str else 999
    except ValueError:
        serial_no = 999
        
    parent_id = int(parent_id) if parent_id else None
    
    # Check duplicate name
    existing = Department.query.filter_by(name=name).first()
    if existing:
        flash(f"Department with name '{name}' already exists.", "error")
        return redirect(url_for("main.department_index"))
        
    dept = Department(name=name, parent_id=parent_id, serial_no=serial_no)
    db.session.add(dept)
    db.session.commit()
    log_action("create_department", details=f"Created department {name} with serial {serial_no}")
    flash(f"Department '{name}' created successfully.", "success")
    return redirect(url_for("main.department_index"))


@main_bp.post("/admin/departments/save-all")
@directory_admin_required
def departments_save_all():
    from .models import Department
    
    # 1. Check if it's a deletion trigger
    delete_id_str = request.form.get("delete_id")
    if delete_id_str:
        try:
            delete_id = int(delete_id_str)
            dept = Department.query.get(delete_id)
            if dept:
                name = dept.name
                db.session.delete(dept)
                db.session.commit()
                log_action("delete_department", details=f"Deleted department {name}")
                flash(f"Department '{name}' deleted successfully.", "success")
            else:
                flash("Department not found.", "error")
        except Exception as e:
            flash(f"Error deleting department: {e}", "error")
        return redirect(url_for("main.department_index"))

    # 2. Otherwise, update all department records
    depts = Department.query.all()
    updated_count = 0
    
    for d in depts:
        name_val = request.form.get(f"name_{d.id}", "").strip()
        serial_val_str = request.form.get(f"serial_no_{d.id}", "").strip()
        parent_val_str = request.form.get(f"parent_id_{d.id}", "").strip()
        
        # Only update if the name input is present in form (meaning it's displayed)
        if name_val:
            d.name = name_val
            
            try:
                d.serial_no = int(serial_val_str) if serial_val_str else 999
            except ValueError:
                pass
                
            if parent_val_str is not None:
                parent_id = int(parent_val_str) if parent_val_str else None
                if parent_id != d.id: # Prevent self-reference
                    d.parent_id = parent_id
            
            updated_count += 1
            
    db.session.commit()
    log_action("bulk_edit_departments", details=f"Bulk updated {updated_count} departments")
    flash("All department changes saved successfully.", "success")
    return redirect(url_for("main.department_index"))


@main_bp.get("/admin/settings")
@service_admin_required
def settings_index():
    return render_template("admin/settings.html")


@main_bp.post("/admin/settings")
@service_admin_required
def settings_save():
    import os
    from flask import current_app
    from .models import Setting
    
    app_name_val = request.form.get("app_name", "").strip()
    if app_name_val:
        setting = Setting.query.get("app_name")
        if not setting:
            setting = Setting(key="app_name")
            db.session.add(setting)
        setting.value = app_name_val
        
    logo_file = request.files.get("logo")
    if logo_file and logo_file.filename:
        filename = "branding_logo.png"
        # Uploads are saved under the dynamic upload folder (served as static/uploads/...)
        save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
        logo_file.save(save_path)
        
        setting = Setting.query.get("logo_path")
        if not setting:
            setting = Setting(key="logo_path")
            db.session.add(setting)
        setting.value = f"uploads/{filename}"
        
    db.session.commit()
    log_action("update_branding_settings", details=f"Updated app name to {app_name_val}")
    flash("Branding settings updated successfully.", "success")
    return redirect(url_for("main.settings_index"))


@main_bp.get("/healthz")
def healthz():
    return {"status": "ok"}


@main_bp.get("/manifest.json")
def manifest_json():
    from flask import send_from_directory, current_app
    import os
    return send_from_directory(os.path.join(current_app.root_path, "static"), "manifest.json")


@main_bp.get("/sw.js")
def service_worker():
    from flask import send_from_directory, current_app
    import os
    return send_from_directory(os.path.join(current_app.root_path, "static", "js"), "sw.js")


# ─────────────────────────────────────────
# Internal Services & Links Directory
# ─────────────────────────────────────────

def _services_access_check():
    """Returns (enabled, visibility) tuple. Aborts 404 for non-admins if not accessible."""
    from .models import Setting
    enabled = Setting.query.get("services_page_enabled")
    visibility = Setting.query.get("services_page_visibility")
    is_enabled = (enabled and enabled.value == "1")
    vis = visibility.value if visibility else "all"
    user = g.current_user
    if not is_enabled:
        if not user or not (user.is_admin or getattr(user, "is_service_admin", False)):
            abort(404)
    elif vis == "admin" and not (user.is_admin or getattr(user, "is_service_admin", False)):
        abort(404)
    return is_enabled, vis


@main_bp.get("/services")
@login_required
def services_index():
    from .models import ServiceLink, Setting
    _services_access_check()
    services = ServiceLink.query.order_by(ServiceLink.sort_order).all()
    categories = sorted(set(s.category for s in services))
    teams = sorted(set(s.managing_team for s in services if s.managing_team))
    enabled_setting = Setting.query.get("services_page_enabled")
    vis_setting = Setting.query.get("services_page_visibility")
    from .models import Employee
    active_employees = Employee.query.filter_by(is_active=True).order_by(Employee.full_name).all()
    return render_template(
        "services/index.html",
        services=services,
        categories=categories,
        teams=teams,
        active_employees=active_employees,
        services_enabled=(enabled_setting.value == "1" if enabled_setting else True),
        services_visibility=(vis_setting.value if vis_setting else "all"),
    )


@main_bp.post("/services/add")
@service_admin_required
def services_add():
    from .models import ServiceLink
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    category = request.form.get("category", "").strip()
    managing_team = request.form.get("managing_team", "").strip()
    contact_person = request.form.get("contact_person", "").strip()
    if not name or not url or not category:
        flash("Name, URL and Category are required.", "error")
        return redirect(url_for("main.services_index"))
    if not (url.startswith("http://") or url.startswith("https://")):
        flash("URL must start with http:// or https://", "error")
        return redirect(url_for("main.services_index"))
    if ServiceLink.query.filter_by(name=name).first():
        flash(f"A service named '{name}' already exists.", "error")
        return redirect(url_for("main.services_index"))
    max_order = db.session.query(func.max(ServiceLink.sort_order)).scalar() or 0
    svc = ServiceLink(
        name=name,
        url=url,
        category=category,
        managing_team=managing_team,
        contact_person=contact_person or None,
        sort_order=max_order + 1
    )
    db.session.add(svc)
    log_action("create_service_link", details=f"Added service link '{name}' with URL '{url}' in category '{category}'")
    db.session.commit()
    flash(f"'{name}' added to the services directory.", "success")
    return redirect(url_for("main.services_index"))


@main_bp.post("/services/<int:svc_id>/edit")
@service_admin_required
def services_edit(svc_id):
    from .models import ServiceLink
    svc = ServiceLink.query.get_or_404(svc_id)
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    category = request.form.get("category", "").strip()
    managing_team = request.form.get("managing_team", "").strip()
    contact_person = request.form.get("contact_person", "").strip()
    if not name or not url or not category:
        flash("Name, URL and Category are required.", "error")
        return redirect(url_for("main.services_index"))
    if not (url.startswith("http://") or url.startswith("https://")):
        flash("URL must start with http:// or https://", "error")
        return redirect(url_for("main.services_index"))
    existing = ServiceLink.query.filter_by(name=name).first()
    if existing and existing.id != svc_id:
        flash(f"Another service named '{name}' already exists.", "error")
        return redirect(url_for("main.services_index"))
    svc.name = name
    svc.url = url
    svc.category = category
    svc.managing_team = managing_team
    svc.contact_person = contact_person or None
    log_action("edit_service_link", details=f"Updated service link '{name}' (URL: '{url}', category: '{category}')")
    db.session.commit()
    flash(f"'{name}' updated successfully.", "success")
    return redirect(url_for("main.services_index"))


@main_bp.post("/services/<int:svc_id>/delete")
@service_admin_required
def services_delete(svc_id):
    from .models import ServiceLink
    svc = ServiceLink.query.get_or_404(svc_id)
    name = svc.name
    db.session.delete(svc)
    log_action("delete_service_link", details=f"Removed service link '{name}'")
    db.session.commit()
    flash(f"'{name}' removed from the directory.", "success")
    return redirect(url_for("main.services_index"))


@main_bp.post("/admin/services-visibility")
@service_admin_required
def services_visibility_update():
    from .models import Setting
    enabled = request.form.get("services_enabled") == "1"
    visibility = request.form.get("services_visibility", "all")
    for key, val in [("services_page_enabled", "1" if enabled else "0"), ("services_page_visibility", visibility)]:
        s = Setting.query.get(key)
        if not s:
            s = Setting(key=key)
            db.session.add(s)
        s.value = val
    log_action("update_services_visibility", details=f"Updated services visibility page setting: enabled={enabled}, visibility={visibility}")
    db.session.commit()
    flash("Services page settings updated.", "success")
    return redirect(url_for("main.settings_index"))


# ─────────────────────────────────────────
# Ticketing Portal (Issue Tracker)
# ─────────────────────────────────────────
import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import send_from_directory, current_app

def _allowed_file(filename):
    # Support common image formats, document formats, compressed files
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'zip', 'rar'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@main_bp.get("/tickets")
@login_required
def tickets_index():
    from .models import Ticket, User
    user = g.current_user
    status_filter = request.args.get("status", "").strip()
    category_filter = request.args.get("category", "").strip()
    priority_filter = request.args.get("priority", "").strip()
    
    if user.is_admin:
        # Admin Queue
        query = Ticket.query
        assigned_to_me = request.args.get("assigned_to_me") == "1"
        if assigned_to_me:
            query = query.filter(Ticket.assigned_to_id == user.id)
            
        # Stats
        total_tickets = Ticket.query.count()
        unassigned_count = Ticket.query.filter(Ticket.assigned_to_id.is_(None)).count()
        critical_count = Ticket.query.filter(Ticket.priority.in_(["Critical", "High"]), Ticket.status.notin_(["Resolved", "Closed"])).count()
        resolved_count = Ticket.query.filter(Ticket.status.in_(["Resolved", "Closed"])).count()
    else:
        # Standard User Dashboard
        query = Ticket.query.filter(Ticket.user_id == user.id)
        total_tickets = query.count()
        unassigned_count = None
        critical_count = query.filter(Ticket.priority.in_(["Critical", "High"]), Ticket.status.notin_(["Resolved", "Closed"])).count()
        resolved_count = query.filter(Ticket.status.in_(["Resolved", "Closed"])).count()

    if status_filter:
        query = query.filter(Ticket.status == status_filter)
    if category_filter:
        query = query.filter(Ticket.category == category_filter)
    if priority_filter:
        query = query.filter(Ticket.priority == priority_filter)

    tickets = query.order_by(Ticket.created_at.desc()).all()
    admins = User.query.filter_by(is_admin=True).all()

    return render_template(
        "tickets/index.html",
        tickets=tickets,
        total_tickets=total_tickets,
        unassigned_count=unassigned_count,
        critical_count=critical_count,
        resolved_count=resolved_count,
        status_filter=status_filter,
        category_filter=category_filter,
        priority_filter=priority_filter,
        admins=admins,
        assigned_to_me=request.args.get("assigned_to_me") == "1" if user.is_admin else False,
    )


@main_bp.get("/tickets/new")
@login_required
def tickets_new():
    user = g.current_user
    # Find matching employee profile if it exists to get company info
    emp = None
    if user.employee_id:
        emp = Employee.query.filter_by(employee_id=user.employee_id).first()
    elif user.email:
        emp = Employee.query.filter(func.lower(Employee.email) == user.email.lower()).first()
        
    return render_template("tickets/new.html", user=user, employee=emp)


@main_bp.post("/tickets/new")
@login_required
def tickets_create():
    from .models import Ticket
    user = g.current_user
    category = request.form.get("category", "").strip()
    subject = request.form.get("subject", "").strip()
    description = request.form.get("description", "").strip()
    priority = request.form.get("priority", "Normal").strip()

    if not category or not subject or not description:
        flash("Category, Subject, and Description are required.", "error")
        return redirect(url_for("main.tickets_new"))

    # Handle optional file attachment
    attachment_path = None
    file = request.files.get("attachment")
    if file and file.filename:
        if _allowed_file(file.filename):
            # Check 3MB size limit
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            if file_size > 3 * 1024 * 1024:
                flash("Attachment file size exceeds the 3MB limit.", "error")
                return redirect(url_for("main.tickets_new"))
                
            # Safe unique filename
            ext = file.filename.rsplit('.', 1)[1].lower()
            unique_name = f"ticket_{uuid.uuid4().hex}.{ext}"
            upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "tickets")
            os.makedirs(upload_dir, exist_ok=True)
            file.save(os.path.join(upload_dir, unique_name))
            attachment_path = f"uploads/tickets/{unique_name}"
        else:
            flash("Invalid file extension. Please upload a valid document or image.", "error")
            return redirect(url_for("main.tickets_new"))

    # Generate Ticket Number: TIC-YYYYMMDD-XXXX
    today_str = datetime.now().strftime("%Y%m%d")
    count_today = Ticket.query.filter(Ticket.ticket_no.like(f"TIC-{today_str}-%")).count()
    ticket_no = f"TIC-{today_str}-{str(count_today + 1).zfill(4)}"

    ticket = Ticket(
        ticket_no=ticket_no,
        user_id=user.id,
        category=category,
        subject=subject,
        description=description,
        priority=priority,
        status="Open",
        attachment_path=attachment_path
    )
    db.session.add(ticket)
    db.session.flush() # Populate ticket.id

    # Notify all Support Admins and Super Admins
    from .models import User as UserModel, Notification
    support_admins = UserModel.query.filter(
        (UserModel.is_admin == True) | (UserModel.is_support_admin == True)
    ).all()
    
    for admin in support_admins:
        if admin.id != user.id: # Avoid self-notification if admin submitted the ticket
            db.session.add(Notification(
                user_id=admin.id,
                ticket_id=ticket.id,
                message=f"🎫 New ticket #{ticket.ticket_no} submitted by {user.display_name}: {subject}"
            ))

    db.session.commit()
    
    log_action("create_ticket", details=f"Created ticket {ticket_no}: {subject}")
    flash(f"Ticket {ticket_no} submitted successfully.", "success")
    return redirect(url_for("main.tickets_index"))


@main_bp.get("/tickets/<int:ticket_id>")
@login_required
def tickets_detail(ticket_id):
    from .models import Ticket, User
    ticket = Ticket.query.get_or_404(ticket_id)
    user = g.current_user

    # Privacy constraint check
    if not user.is_admin and ticket.user_id != user.id:
        abort(403)

    admins = User.query.filter_by(is_admin=True).all()
    return render_template("tickets/detail.html", ticket=ticket, admins=admins)


@main_bp.post("/tickets/<int:ticket_id>/comment")
@login_required
def tickets_comment(ticket_id):
    from .models import Ticket, TicketComment
    ticket = Ticket.query.get_or_404(ticket_id)
    user = g.current_user

    # Privacy check
    if not user.is_admin and ticket.user_id != user.id:
        abort(403)

    body = request.form.get("body", "").strip()
    is_internal = request.form.get("is_internal") == "1" and user.is_admin

    if not body:
        flash("Comment content cannot be empty.", "error")
        return redirect(url_for("main.tickets_detail", ticket_id=ticket.id))

    # Handle file upload in comment
    attachment_path = None
    file = request.files.get("attachment")
    if file and file.filename:
        if _allowed_file(file.filename):
            # Check 3MB size limit
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            if file_size > 3 * 1024 * 1024:
                flash("Attachment file size exceeds the 3MB limit.", "error")
                return redirect(url_for("main.tickets_detail", ticket_id=ticket.id))

            ext = file.filename.rsplit('.', 1)[1].lower()
            unique_name = f"comment_{uuid.uuid4().hex}.{ext}"
            upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "tickets")
            os.makedirs(upload_dir, exist_ok=True)
            file.save(os.path.join(upload_dir, unique_name))
            attachment_path = f"uploads/tickets/{unique_name}"
        else:
            flash("Invalid file extension.", "error")
            return redirect(url_for("main.tickets_detail", ticket_id=ticket.id))

    # Auto-assign ticket to the commenting support agent if they are not already assigned
    from .models import Notification
    if user.is_admin and ticket.assigned_to_id != user.id:
        ticket.assigned_to_id = user.id
        auto_note = TicketComment(
            ticket_id=ticket.id,
            user_id=user.id,
            body=f"[System Auto Note] Ticket auto-assigned to {user.display_name} due to comment activity.",
            is_internal=True
        )
        db.session.add(auto_note)

    comment = TicketComment(
        ticket_id=ticket.id,
        user_id=user.id,
        body=body,
        attachment_path=attachment_path,
        is_internal=is_internal
    )
    db.session.add(comment)
    
    # Touch ticket's updated_at timestamp
    ticket.updated_at = datetime.utcnow()
    
    # Trigger notifications
    if user.id == ticket.user_id:
        # Reporter commented -> Notify assignee if set
        if ticket.assigned_to_id:
            db.session.add(Notification(
                user_id=ticket.assigned_to_id,
                ticket_id=ticket.id,
                message=f"New comment from {user.display_name} on Ticket #{ticket.ticket_no}."
            ))
    else:
        # Someone else (e.g. support agent) commented -> Notify reporter (unless internal note)
        if not is_internal:
            db.session.add(Notification(
                user_id=ticket.user_id,
                ticket_id=ticket.id,
                message=f"Support agent {user.display_name} replied to Ticket #{ticket.ticket_no}."
            ))
            
    db.session.commit()
    flash("Comment posted.", "success")
    return redirect(url_for("main.tickets_detail", ticket_id=ticket.id))


@main_bp.post("/tickets/<int:ticket_id>/update")
@support_admin_required
def tickets_update(ticket_id):
    from .models import Ticket, TicketComment, Notification, User
    ticket = Ticket.query.get_or_404(ticket_id)
    user = g.current_user
    
    status = request.form.get("status", "").strip()
    priority = request.form.get("priority", "").strip()
    assigned_to_id = request.form.get("assigned_to_id", "").strip()

    changes = []
    if status and status != ticket.status:
        changes.append(f"status changed from '{ticket.status}' to '{status}'")
        ticket.status = status
    if priority and priority != ticket.priority:
        changes.append(f"priority changed from '{ticket.priority}' to '{priority}'")
        ticket.priority = priority
        
    if assigned_to_id == "unassigned":
        if ticket.assigned_to_id is not None:
            changes.append("assignment removed (unassigned)")
            ticket.assigned_to_id = None
    elif assigned_to_id:
        try:
            aid = int(assigned_to_id)
            if aid != ticket.assigned_to_id:
                assignee_user = User.query.get(aid)
                assignee_name = assignee_user.display_name if assignee_user else f"User ID {aid}"
                changes.append(f"assigned to '{assignee_name}'")
                ticket.assigned_to_id = aid
        except ValueError:
            pass
    else:
        # If no explicit assignment changes were submitted, but the ticket is unassigned 
        # or assigned to someone else, auto-assign it to the current support agent making changes
        if ticket.assigned_to_id != user.id:
            ticket.assigned_to_id = user.id
            changes.append(f"assigned to '{user.display_name}' (auto-assigned due to activity)")

    if changes:
        ticket.updated_at = datetime.utcnow()
        
        # Add automated internal note recording the changes
        change_note = TicketComment(
            ticket_id=ticket.id,
            user_id=user.id,
            body="[System Auto Note] Ticket fields updated:\n- " + "\n- ".join(changes),
            is_internal=True
        )
        db.session.add(change_note)

        # Notify reporter of updates (unless the reporter is the support agent making changes)
        if ticket.user_id != user.id:
            db.session.add(Notification(
                user_id=ticket.user_id,
                ticket_id=ticket.id,
                message=f"Your Ticket #{ticket.ticket_no} was updated by {user.display_name}: {', '.join(changes)}."
            ))

        # Notify assigned agent if assigned and not the current user
        if ticket.assigned_to_id and ticket.assigned_to_id != user.id:
            db.session.add(Notification(
                user_id=ticket.assigned_to_id,
                ticket_id=ticket.id,
                message=f"Ticket #{ticket.ticket_no} has been assigned to you by {user.display_name}."
            ))

        db.session.commit()
        log_action("update_ticket", details=f"Updated ticket fields: {', '.join(changes)}")
        flash("Ticket updated successfully.", "success")
    else:
        flash("No changes made.", "info")

    return redirect(url_for("main.tickets_detail", ticket_id=ticket.id))


# ─────────────────────────────────────────
# Notification Management
# ─────────────────────────────────────────

@main_bp.get("/notifications")
@login_required
def notifications_index():
    from .models import Notification
    user = g.current_user
    notifications = Notification.query.filter_by(user_id=user.id).order_by(Notification.created_at.desc()).all()
    return render_template("notifications.html", notifications=notifications)


@main_bp.post("/notifications/read-all")
@login_required
def notifications_read_all():
    from .models import Notification
    user = g.current_user
    Notification.query.filter_by(user_id=user.id, is_read=False).update({Notification.is_read: True})
    db.session.commit()
    flash("All notifications marked as read.", "success")
    return redirect(url_for("main.notifications_index"))


@main_bp.get("/notifications/<int:notif_id>/read")
@login_required
def notification_read_redirect(notif_id):
    from .models import Notification
    user = g.current_user
    notif = Notification.query.filter_by(id=notif_id, user_id=user.id).first_or_404()
    notif.is_read = True
    db.session.commit()
    if notif.ticket_id:
        return redirect(url_for("main.tickets_detail", ticket_id=notif.ticket_id))
    if getattr(notif, "clearance_request_id", None):
        return redirect(url_for("main.clearance_detail", request_id=notif.clearance_request_id))
    return redirect(url_for("main.notifications_index"))


@main_bp.get("/api/notifications/unread-count")
@login_required
def api_notifications_unread_count():
    from .models import Notification
    count = Notification.query.filter_by(user_id=g.current_user.id, is_read=False).count()
    return {"unread_count": count}


# ─────────────────────────────────────────────────────────────────────────────
# Technology Clearance Flow
# ─────────────────────────────────────────────────────────────────────────────

def _is_clearance_user(user):
    """Return True if user is a clearance initiator, approver, clearance admin, or super admin."""
    from .models import ClearanceInitiator, ClearanceApproverConfig
    if user.is_admin or getattr(user, 'is_clearance_admin', False):
        return True
    if ClearanceInitiator.query.filter_by(user_id=user.id).first():
        return True
    if ClearanceApproverConfig.query.filter_by(user_id=user.id).first():
        return True
    return False


def _run_clearance_background():
    """Run reminder notifications and auto-deactivations inline."""
    from datetime import date
    from .models import (
        ClearanceRequest, Notification, CLEARANCE_REMINDER_DAYS, AuditLog
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
            for threshold in CLEARANCE_REMINDER_DAYS:
                if days_elapsed >= threshold and threshold not in approval.days_reminded:
                    db.session.add(Notification(
                        user_id=approval.approver_user_id,
                        message=(
                            f"\u23f0 Reminder (Day {threshold}): Clearance {req.request_no} for "
                            f"{req.employee.full_name} is awaiting your approval."
                        ),
                    ))
                    approval.mark_reminded(threshold)
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


# ── Clearance Admin: Config ───────────────────────────────────────────────────

@main_bp.get("/clearance/admin/config")
@clearance_admin_required
def clearance_config():
    from .models import ClearanceInitiator, ClearanceApproverConfig, User
    initiators = ClearanceInitiator.query.order_by(ClearanceInitiator.created_at).all()
    approvers = ClearanceApproverConfig.query.order_by(ClearanceApproverConfig.sort_order).all()
    initiator_ids = {i.user_id for i in initiators}
    approver_ids = {a.user_id for a in approvers}
    all_users = User.query.order_by(User.full_name).all()
    return render_template(
        "clearance/config.html",
        initiators=initiators, approvers=approvers,
        all_users=all_users, initiator_ids=initiator_ids, approver_ids=approver_ids,
    )


@main_bp.post("/clearance/admin/config/initiator/add")
@clearance_admin_required
def clearance_config_add_initiator():
    from .models import ClearanceInitiator, User
    user_id = request.form.get("user_id", "").strip()
    if not user_id:
        flash("Please select a user.", "error")
        return redirect(url_for("main.clearance_config"))
    user = User.query.get(int(user_id))
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("main.clearance_config"))
    if ClearanceInitiator.query.filter_by(user_id=user.id).first():
        flash(f"{user.display_name} is already an initiator.", "info")
        return redirect(url_for("main.clearance_config"))
    db.session.add(ClearanceInitiator(user_id=user.id, added_by_id=g.current_user.id))
    log_action("clearance_add_initiator", details=f"Added {user.display_name} as clearance initiator")
    db.session.commit()
    flash(f"{user.display_name} added as a clearance initiator.", "success")
    return redirect(url_for("main.clearance_config"))


@main_bp.post("/clearance/admin/config/initiator/<int:entry_id>/remove")
@clearance_admin_required
def clearance_config_remove_initiator(entry_id):
    from .models import ClearanceInitiator
    entry = ClearanceInitiator.query.get_or_404(entry_id)
    name = entry.user.display_name
    db.session.delete(entry)
    log_action("clearance_remove_initiator", details=f"Removed {name} from clearance initiators")
    db.session.commit()
    flash(f"{name} removed from clearance initiators.", "success")
    return redirect(url_for("main.clearance_config"))


@main_bp.post("/clearance/admin/config/approver/add")
@clearance_admin_required
def clearance_config_add_approver():
    from .models import ClearanceApproverConfig, User
    user_id = request.form.get("user_id", "").strip()
    label = request.form.get("label", "").strip()
    if not user_id:
        flash("Please select a user.", "error")
        return redirect(url_for("main.clearance_config"))
    user = User.query.get(int(user_id))
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("main.clearance_config"))
    if ClearanceApproverConfig.query.filter_by(user_id=user.id).first():
        flash(f"{user.display_name} is already an approver.", "info")
        return redirect(url_for("main.clearance_config"))
    max_order = db.session.query(func.max(ClearanceApproverConfig.sort_order)).scalar() or 0
    db.session.add(ClearanceApproverConfig(
        user_id=user.id, label=label or None,
        sort_order=max_order + 1, added_by_id=g.current_user.id
    ))
    log_action("clearance_add_approver", details=f"Added {user.display_name} as clearance approver (label: {label or 'none'})")
    db.session.commit()
    flash(f"{user.display_name} added as a clearance approver.", "success")
    return redirect(url_for("main.clearance_config"))


@main_bp.post("/clearance/admin/config/approver/<int:entry_id>/remove")
@clearance_admin_required
def clearance_config_remove_approver(entry_id):
    from .models import ClearanceApproverConfig
    entry = ClearanceApproverConfig.query.get_or_404(entry_id)
    name = entry.user.display_name
    db.session.delete(entry)
    log_action("clearance_remove_approver", details=f"Removed {name} from clearance approvers")
    db.session.commit()
    flash(f"{name} removed from clearance approvers.", "success")
    return redirect(url_for("main.clearance_config"))


@main_bp.post("/clearance/admin/config/approver/<int:entry_id>/label")
@clearance_admin_required
def clearance_config_update_label(entry_id):
    from .models import ClearanceApproverConfig
    entry = ClearanceApproverConfig.query.get_or_404(entry_id)
    entry.label = request.form.get("label", "").strip() or None
    db.session.commit()
    flash("Label updated.", "success")
    return redirect(url_for("main.clearance_config"))


# ── Clearance Admin: Tracking Dashboard ──────────────────────────────────────

@main_bp.get("/clearance/admin/tracking")
@clearance_admin_required
def clearance_tracking():
    from .models import ClearanceRequest
    _run_clearance_background()
    ongoing = ClearanceRequest.query.filter(
        ClearanceRequest.status.in_(['pending', 'in_progress'])
    ).order_by(ClearanceRequest.created_at.desc()).all()
    completed = ClearanceRequest.query.filter(
        ClearanceRequest.status.in_(['cleared', 'cancelled'])
    ).order_by(ClearanceRequest.updated_at.desc()).all()
    return render_template("clearance/tracking.html", ongoing=ongoing, completed=completed)


# ── Initiator: My Clearances ──────────────────────────────────────────────────

@main_bp.get("/clearance/")
@login_required
def clearance_index():
    from .models import ClearanceInitiator, ClearanceApproverConfig, ClearanceApproval
    user = g.current_user
    _run_clearance_background()
    if user.is_admin or user.is_clearance_admin:
        from .models import ClearanceRequest
        my_requests = ClearanceRequest.query.order_by(ClearanceRequest.created_at.desc()).all()
        # Admins can also be configured as approvers, so load their pending approvals too
        my_approvals = ClearanceApproval.query.filter_by(
            approver_user_id=user.id, status='pending'
        ).order_by(ClearanceApproval.id.desc()).all()
    else:
        is_initiator = ClearanceInitiator.query.filter_by(user_id=user.id).first()
        is_approver_cfg = ClearanceApproverConfig.query.filter_by(user_id=user.id).first()
        from .models import ClearanceRequest
        my_requests = []
        my_approvals = []
        if is_initiator:
            my_requests = ClearanceRequest.query.filter_by(
                initiated_by_id=user.id
            ).order_by(ClearanceRequest.created_at.desc()).all()
        if is_approver_cfg:
            my_approvals = ClearanceApproval.query.filter_by(
                approver_user_id=user.id, status='pending'
            ).order_by(ClearanceApproval.id.desc()).all()

    if not _is_clearance_user(user):
        abort(403)

    can_initiate = (user.is_admin or user.is_clearance_admin or
                    bool(ClearanceInitiator.query.filter_by(user_id=user.id).first()))
                    
    # Calculate stats for the dashboard count board
    # For admins/clearance admins: show stats of all requests in system
    # For non-admin approvers who only have approvals: total/active/done matching their assigned requests
    if user.is_admin or user.is_clearance_admin:
        from .models import ClearanceRequest
        stats_requests = ClearanceRequest.query.all()
    else:
        # Load all requests that this non-admin user initiated or is an approver for
        from .models import ClearanceRequest, ClearanceApproval
        initiated = ClearanceRequest.query.filter_by(initiated_by_id=user.id).all()
        assigned_approvals = ClearanceApproval.query.filter_by(approver_user_id=user.id).all()
        assigned_req_ids = {a.request_id for a in assigned_approvals}
        stats_requests = list(initiated)
        if assigned_req_ids:
            stats_requests += ClearanceRequest.query.filter(ClearanceRequest.id.in_(list(assigned_req_ids))).all()
        # Remove duplicates
        stats_requests = list({r.id: r for r in stats_requests}.values())

    stats_total = len(stats_requests)
    stats_active = len([r for r in stats_requests if r.status in ('pending', 'in_progress')])
    stats_done = len([r for r in stats_requests if r.status == 'cleared'])

    return render_template(
        "clearance/index.html",
        my_requests=my_requests,
        my_approvals=my_approvals,
        can_initiate=can_initiate,
        stats_total=stats_total,
        stats_active=stats_active,
        stats_done=stats_done,
    )


@main_bp.get("/clearance/new")
@login_required
def clearance_new():
    from .models import ClearanceInitiator
    user = g.current_user
    if not (user.is_admin or user.is_clearance_admin or
            ClearanceInitiator.query.filter_by(user_id=user.id).first()):
        abort(403)
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.full_name).all()
    return render_template("clearance/new.html", employees=employees)


@main_bp.post("/clearance/new")
@login_required
def clearance_create():
    from datetime import date as date_type, datetime as dt_type
    from .models import (
        ClearanceInitiator, ClearanceRequest, ClearanceApproval,
        ClearanceApproverConfig, Notification, User as UserModel
    )
    user = g.current_user
    if not (user.is_admin or user.is_clearance_admin or
            ClearanceInitiator.query.filter_by(user_id=user.id).first()):
        abort(403)

    employee_id = request.form.get("employee_id", "").strip()
    lwd_str = request.form.get("last_working_date", "").strip()
    notes = request.form.get("notes", "").strip()

    if not employee_id or not lwd_str:
        flash("Employee and Last Working Date are required.", "error")
        return redirect(url_for("main.clearance_new"))
    try:
        lwd = date_type.fromisoformat(lwd_str)
    except ValueError:
        flash("Invalid date format.", "error")
        return redirect(url_for("main.clearance_new"))

    employee = Employee.query.get_or_404(int(employee_id))
    existing = ClearanceRequest.query.filter(
        ClearanceRequest.employee_id == employee.id,
        ClearanceRequest.status.in_(['pending', 'in_progress'])
    ).first()
    if existing:
        flash(f"An active clearance ({existing.request_no}) already exists for {employee.full_name}.", "error")
        return redirect(url_for("main.clearance_new"))

    today_str = dt_type.now().strftime("%Y%m%d")
    count_today = ClearanceRequest.query.filter(
        ClearanceRequest.request_no.like(f"CLR-{today_str}-%")
    ).count()
    request_no = f"CLR-{today_str}-{str(count_today + 1).zfill(3)}"

    approver_configs = ClearanceApproverConfig.query.order_by(ClearanceApproverConfig.sort_order).all()
    status = 'in_progress' if approver_configs else 'pending'

    clr = ClearanceRequest(
        request_no=request_no, employee_id=employee.id,
        initiated_by_id=user.id, last_working_date=lwd,
        status=status, notes=notes or None,
    )
    db.session.add(clr)
    db.session.flush()

    for idx, cfg in enumerate(approver_configs):
        db.session.add(ClearanceApproval(
            request_id=clr.id, approver_user_id=cfg.user_id,
            label=cfg.label, sort_order=idx + 1,
        ))
        db.session.add(Notification(
            user_id=cfg.user_id,
            clearance_request_id=clr.id,
            message=(
                f"\U0001f4cb New clearance {request_no} submitted for {employee.full_name}. "
                f"Last working date: {lwd.strftime('%d %b %Y')}. Your approval is needed."
            )
        ))

    for admin in UserModel.query.filter(
        (UserModel.is_clearance_admin == True) | (UserModel.is_admin == True)
    ).all():
        if admin.id != user.id:
            db.session.add(Notification(
                user_id=admin.id,
                clearance_request_id=clr.id,
                message=f"\U0001f4cb New clearance {request_no} submitted by {user.display_name} for {employee.full_name}."
            ))

    log_action("create_clearance", employee=employee,
               details=f"Created clearance {request_no}, LWD: {lwd}")
    db.session.commit()
    flash(f"Clearance request {request_no} submitted successfully.", "success")
    return redirect(url_for("main.clearance_detail", request_id=clr.id))


@main_bp.get("/clearance/<int:request_id>")
@login_required
def clearance_detail(request_id):
    from .models import ClearanceRequest
    user = g.current_user
    req = ClearanceRequest.query.get_or_404(request_id)
    is_admin_access = user.is_admin or getattr(user, 'is_clearance_admin', False)
    is_initiator = req.initiated_by_id == user.id
    is_approver = any(a.approver_user_id == user.id for a in req.approvals)
    if not (is_admin_access or is_initiator or is_approver):
        abort(403)
    my_approval = next((a for a in req.approvals if a.approver_user_id == user.id), None)
    return render_template(
        "clearance/detail.html",
        req=req, my_approval=my_approval,
        is_admin_access=is_admin_access, is_initiator=is_initiator,
    )


@main_bp.post("/clearance/<int:request_id>/cancel")
@login_required
def clearance_cancel(request_id):
    from .models import ClearanceRequest, Notification
    user = g.current_user
    req = ClearanceRequest.query.get_or_404(request_id)
    if not (user.is_admin or getattr(user, 'is_clearance_admin', False) or req.initiated_by_id == user.id):
        abort(403)
    if req.status not in ('pending', 'in_progress'):
        flash("This clearance cannot be cancelled.", "error")
        return redirect(url_for("main.clearance_detail", request_id=req.id))
    req.status = 'cancelled'
    if req.initiated_by_id != user.id:
        db.session.add(Notification(
            user_id=req.initiated_by_id,
            message=f"\u274c Clearance {req.request_no} for {req.employee.full_name} was cancelled by {user.display_name}."
        ))
    log_action("cancel_clearance", employee=req.employee, details=f"Cancelled clearance {req.request_no}")
    db.session.commit()
    flash(f"Clearance {req.request_no} has been cancelled.", "success")
    return redirect(url_for("main.clearance_index"))


@main_bp.post("/clearance/approval/<int:approval_id>/clear")
@login_required
def clearance_approval_clear(approval_id):
    from datetime import datetime as dt_type, timezone, date as date_type
    from .models import ClearanceApproval, Notification, AuditLog, User as UserModel
    user = g.current_user
    approval = ClearanceApproval.query.get_or_404(approval_id)
    if approval.approver_user_id != user.id and not (user.is_admin or getattr(user, 'is_clearance_admin', False)):
        abort(403)
    if approval.status == 'cleared':
        flash("This approval has already been submitted.", "info")
        return redirect(url_for("main.clearance_detail", request_id=approval.request_id))

    approval.status = 'cleared'
    approval.comment = request.form.get("comment", "").strip() or None
    approval.cleared_at = dt_type.now(timezone.utc)
    db.session.flush()

    req = approval.request
    if req.all_cleared:
        req.status = 'cleared'
        today = date_type.today()
        if req.last_working_date <= today:
            req.employee.is_active = False
            db.session.add(AuditLog(
                actor_email='system', action='auto_deactivate_employee',
                target_employee_id=req.employee.employee_id,
                details=f"Auto-deactivated via clearance {req.request_no}. LWD: {req.last_working_date}"
            ))
        db.session.add(Notification(
            user_id=req.initiated_by_id,
            clearance_request_id=req.id,
            message=f"\u2705 Clearance {req.request_no} for {req.employee.full_name} is fully cleared by all approvers."
        ))
        for a in req.approvals:
            if a.approver_user_id != req.initiated_by_id:
                db.session.add(Notification(
                    user_id=a.approver_user_id,
                    clearance_request_id=req.id,
                    message=f"\u2705 Clearance {req.request_no} for {req.employee.full_name} is now fully cleared."
                ))
        for admin in UserModel.query.filter(
            (UserModel.is_clearance_admin == True) | (UserModel.is_admin == True)
        ).all():
            if admin.id != req.initiated_by_id:
                db.session.add(Notification(
                    user_id=admin.id,
                    clearance_request_id=req.id,
                    message=f"\u2705 Clearance {req.request_no} for {req.employee.full_name} has been fully approved."
                ))
        flash(f"All approvers have cleared — clearance {req.request_no} is complete!", "success")
    else:
        cleared_count = len(req.cleared_approvals)
        total_count = len(req.approvals)
        db.session.add(Notification(
            user_id=req.initiated_by_id,
            clearance_request_id=req.id,
            message=(
                f"\U0001f4ca Clearance {req.request_no}: {cleared_count}/{total_count} approvers done. "
                f"{user.display_name} just approved."
            )
        ))
        flash("Your clearance approval submitted successfully.", "success")

    log_action("clearance_approval", employee=req.employee,
               details=f"Approved clearance {req.request_no} by {user.display_name}")
    db.session.commit()
    return redirect(url_for("main.clearance_detail", request_id=req.id))


# ─────────────────────────────────────────────────────────────────────────────
# Expiration Reminder Flow Routes
# ─────────────────────────────────────────────────────────────────────────────
import csv
import io
from datetime import date, datetime

@main_bp.get("/reminders")
@reminder_viewer_required
def reminder_index():
    from .models import ExpirationReminder, ExpirationReminderCategory
    from .cli import _process_expiration_reminders_background
    _run_clearance_background() # Execute background task triggers
    _process_expiration_reminders_background()
    
    status_filter = request.args.get("status", "").strip()
    category_filter = request.args.get("category", "").strip()
    
    query = ExpirationReminder.query
    if status_filter:
        today = date.today()
        if status_filter == "expired":
            query = query.filter(ExpirationReminder.expiry_date < today)
        elif status_filter == "critical":
            query = query.filter(ExpirationReminder.expiry_date >= today, (ExpirationReminder.expiry_date - today).days <= 30)
        elif status_filter == "warning":
            query = query.filter((ExpirationReminder.expiry_date - today).days > 30, (ExpirationReminder.expiry_date - today).days <= 60)
        elif status_filter == "ok":
            query = query.filter((ExpirationReminder.expiry_date - today).days > 60)
            
    if category_filter:
        query = query.filter(ExpirationReminder.category_id == int(category_filter))
        
    reminders = query.order_by(ExpirationReminder.expiry_date.asc()).all()
    categories = ExpirationReminderCategory.query.order_by(ExpirationReminderCategory.name).all()
    
    # Calculate stat summary
    today = date.today()
    all_items = ExpirationReminder.query.all()
    stats = {"expired": 0, "critical": 0, "warning": 0, "ok": 0}
    for item in all_items:
        stats[item.status] += 1
        
    return render_template(
        "reminders/index.html",
        reminders=reminders,
        categories=categories,
        stats=stats,
        status_filter=status_filter,
        category_filter=category_filter,
        today=today
    )


@main_bp.get("/reminders/new")
@reminder_admin_required
def reminder_new():
    from .models import ExpirationReminderCategory
    categories = ExpirationReminderCategory.query.order_by(ExpirationReminderCategory.name).all()
    return render_template("reminders/new.html", categories=categories)


@main_bp.post("/reminders/new")
@reminder_admin_required
def reminder_create():
    from .models import ExpirationReminder
    
    license_name = request.form.get("license_name", "").strip()
    stored_location = request.form.get("stored_location", "").strip()
    system_app_used = request.form.get("system_app_used", "").strip()
    system_owner = request.form.get("system_owner", "").strip()
    vendor_info = request.form.get("vendor_info", "").strip()
    expiry_date_str = request.form.get("expiry_date", "").strip()
    category_id = request.form.get("category_id", "").strip()
    path_notes = request.form.get("path_notes", "").strip()
    
    if not license_name or not expiry_date_str:
        flash("License Name and Expiry Date are required.", "error")
        return redirect(url_for("main.reminder_new"))
        
    try:
        expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid Expiry Date format.", "error")
        return redirect(url_for("main.reminder_new"))
        
    cat_id = int(category_id) if category_id else None
    
    reminder = ExpirationReminder(
        license_name=license_name,
        stored_location=stored_location or None,
        system_app_used=system_app_used or None,
        system_owner=system_owner or None,
        vendor_info=vendor_info or None,
        expiry_date=expiry_date,
        category_id=cat_id,
        path_notes=path_notes or None
    )
    db.session.add(reminder)
    db.session.commit()
    
    log_action("create_expiration_reminder", details=f"Created reminder '{license_name}' expiring on {expiry_date}")
    flash(f"Reminder '{license_name}' created successfully.", "success")
    return redirect(url_for("main.reminder_index"))


@main_bp.get("/reminders/<int:reminder_id>")
@reminder_viewer_required
def reminder_detail(reminder_id):
    from .models import ExpirationReminder
    r = ExpirationReminder.query.get_or_404(reminder_id)
    return render_template("reminders/detail.html", reminder=r)


@main_bp.get("/reminders/<int:reminder_id>/edit")
@reminder_admin_required
def reminder_edit(reminder_id):
    from .models import ExpirationReminder, ExpirationReminderCategory
    r = ExpirationReminder.query.get_or_404(reminder_id)
    categories = ExpirationReminderCategory.query.order_by(ExpirationReminderCategory.name).all()
    return render_template("reminders/edit.html", reminder=r, categories=categories)


@main_bp.post("/reminders/<int:reminder_id>/edit")
@reminder_admin_required
def reminder_update(reminder_id):
    from .models import ExpirationReminder
    r = ExpirationReminder.query.get_or_404(reminder_id)
    
    license_name = request.form.get("license_name", "").strip()
    stored_location = request.form.get("stored_location", "").strip()
    system_app_used = request.form.get("system_app_used", "").strip()
    system_owner = request.form.get("system_owner", "").strip()
    vendor_info = request.form.get("vendor_info", "").strip()
    expiry_date_str = request.form.get("expiry_date", "").strip()
    category_id = request.form.get("category_id", "").strip()
    path_notes = request.form.get("path_notes", "").strip()
    
    if not license_name or not expiry_date_str:
        flash("License Name and Expiry Date are required.", "error")
        return redirect(url_for("main.reminder_edit", reminder_id=r.id))
        
    try:
        expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid Expiry Date format.", "error")
        return redirect(url_for("main.reminder_edit", reminder_id=r.id))
        
    r.license_name = license_name
    r.stored_location = stored_location or None
    r.system_app_used = system_app_used or None
    r.system_owner = system_owner or None
    r.vendor_info = vendor_info or None
    r.expiry_date = expiry_date
    r.category_id = int(category_id) if category_id else None
    r.path_notes = path_notes or None
    
    db.session.commit()
    log_action("update_expiration_reminder", details=f"Updated reminder '{license_name}' expiring on {expiry_date}")
    flash(f"Reminder '{license_name}' updated successfully.", "success")
    return redirect(url_for("main.reminder_detail", reminder_id=r.id))


@main_bp.post("/reminders/<int:reminder_id>/delete")
@admin_required
def reminder_delete(reminder_id):
    from .models import ExpirationReminder
    r = ExpirationReminder.query.get_or_404(reminder_id)
    name = r.license_name
    db.session.delete(r)
    db.session.commit()
    log_action("delete_expiration_reminder", details=f"Deleted reminder '{name}'")
    flash(f"Reminder '{name}' deleted successfully.", "success")
    return redirect(url_for("main.reminder_index"))


# ── Reminder Admin: Categories Management ─────────────────────────────────────

@main_bp.post("/reminders/categories/add")
@reminder_admin_required
def reminder_category_add():
    from .models import ExpirationReminderCategory
    name = request.form.get("name", "").strip()
    if not name:
        flash("Category name is required.", "error")
        return redirect(request.referrer or url_for("main.reminder_index"))
        
    existing = ExpirationReminderCategory.query.filter_by(name=name).first()
    if existing:
        flash(f"Category '{name}' already exists.", "info")
        return redirect(request.referrer or url_for("main.reminder_index"))
        
    db.session.add(ExpirationReminderCategory(name=name))
    db.session.commit()
    flash(f"Category '{name}' added successfully.", "success")
    return redirect(request.referrer or url_for("main.reminder_index"))


# ── Reminder Settings: Custom Notification Thresholds ───────────────────────

@main_bp.get("/reminders/settings")
@reminder_admin_required
def reminder_settings():
    from .models import Setting
    days_cfg = Setting.query.get("reminder_days_config")
    days_val = days_cfg.value if days_cfg else "60, 45, 30"
    return render_template("reminders/settings.html", days_val=days_val)


@main_bp.post("/reminders/settings")
@reminder_admin_required
def reminder_settings_save():
    from .models import Setting
    days_val = request.form.get("days_val", "").strip()
    
    # Simple validation for comma-separated integers
    try:
        thresholds = [int(x.strip()) for x in days_val.split(",") if x.strip()]
        if not thresholds:
            raise ValueError()
    except ValueError:
        flash("Please enter a valid comma-separated list of numbers (e.g. 60, 45, 30).", "error")
        return redirect(url_for("main.reminder_settings"))
        
    # Standardize format
    standard_val = ", ".join(str(t) for t in sorted(thresholds, reverse=True))
    
    cfg = Setting.query.get("reminder_days_config")
    if not cfg:
        cfg = Setting(key="reminder_days_config")
        db.session.add(cfg)
    cfg.value = standard_val
    db.session.commit()
    
    log_action("update_reminder_settings", details=f"Updated expiration alert thresholds to: {standard_val}")
    flash(f"Expiration alert thresholds updated to: {standard_val} days.", "success")
    return redirect(url_for("main.reminder_index"))


# ── Expiration Reminder Bulk CSV Import ───────────────────────────────────────

@main_bp.post("/reminders/import")
@reminder_admin_required
def reminder_import():
    from .models import ExpirationReminder, ExpirationReminderCategory
    file = request.files.get("csv_file")
    if not file or not file.filename:
        flash("Please select a CSV file to upload.", "error")
        return redirect(url_for("main.reminder_index"))
        
    if not file.filename.lower().endswith(".csv"):
        flash("Only CSV files are supported for bulk import.", "error")
        return redirect(url_for("main.reminder_index"))
        
    try:
        stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
        reader = csv.DictReader(stream)
        
        # Validate columns slightly
        headers = [h.strip() for h in reader.fieldnames] if reader.fieldnames else []
        required_mappings = {
            "License Name": ["License Name", "license_name", "LicenseName", "Name"],
            "License expiry date": ["License expiry date", "License expiry", "Expiry Date", "expiry_date", "expiry", "License expiry date*"]
        }
        
        # Check mapping matches
        name_col = next((h for h in headers if h in required_mappings["License Name"]), None)
        expiry_col = next((h for h in headers if h in required_mappings["License expiry date"]), None)
        
        if not name_col or not expiry_col:
            flash("CSV must contain at least 'License Name' and 'License expiry date' columns.", "error")
            return redirect(url_for("main.reminder_index"))
            
        # Optional maps
        loc_col = next((h for h in headers if h in ["License stored location", "stored_location", "Location"]), None)
        app_col = next((h for h in headers if h in ["System/application is used this license", "system_app_used", "System", "Application"]), None)
        owner_col = next((h for h in headers if h in ["System Owner", "system_owner", "Owner"]), None)
        vendor_col = next((h for h in headers if h in ["Vendor Info", "vendor_info", "Vendor"]), None)
        cat_col = next((h for h in headers if h in ["Item Type", "ItemType", "Category", "category"]), None)
        path_col = next((h for h in headers if h in ["Path", "path_notes", "Notes", "Path*"]), None)
        
        count = 0
        skipped = 0
        
        # To avoid creating duplicate categories inside the loop
        cached_categories = {c.name.lower(): c for c in ExpirationReminderCategory.query.all()}
        
        for row in reader:
            license_name = (row.get(name_col) or "").strip()
            expiry_str = (row.get(expiry_col) or "").strip()
            
            if not license_name or not expiry_str:
                skipped += 1
                continue
                
            # Date parses: try common formats like 1/11/2027, 2027-01-11, etc.
            expiry_date = None
            date_formats = ["%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%y", "%d/%m/%y", "%Y/%m/%d"]
            for fmt in date_formats:
                try:
                    expiry_date = datetime.strptime(expiry_str, fmt).date()
                    break
                except ValueError:
                    continue
                    
            if not expiry_date:
                skipped += 1
                continue
                
            # Retrieve or create category
            cat_name = (row.get(cat_col) or "Other").strip()
            cat = cached_categories.get(cat_name.lower())
            if not cat:
                cat = ExpirationReminderCategory(name=cat_name)
                db.session.add(cat)
                db.session.flush()
                cached_categories[cat_name.lower()] = cat
                
            # Create Reminder record
            reminder = ExpirationReminder(
                license_name=license_name,
                stored_location=(row.get(loc_col) or "").strip() or None,
                system_app_used=(row.get(app_col) or "").strip() or None,
                system_owner=(row.get(owner_col) or "").strip() or None,
                vendor_info=(row.get(vendor_col) or "").strip() or None,
                expiry_date=expiry_date,
                category_id=cat.id,
                path_notes=(row.get(path_col) or "").strip() or None
            )
            db.session.add(reminder)
            count += 1
            
        db.session.commit()
        log_action("import_expiration_reminders", details=f"Bulk imported {count} expiration reminders from CSV, skipped {skipped}")
        flash(f"Successfully imported {count} reminders from CSV. Skipped {skipped} rows due to empty values or parsing issues.", "success")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error parsing CSV: {e}", "error")
        
    return redirect(url_for("main.reminder_index"))
