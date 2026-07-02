import json
from pathlib import Path

from .models import Employee, db
from .utils import normalize_email


def seed_if_empty(app):
    if Employee.query.first():
        return 0

    seed_path = Path(app.config["SEED_JSON_PATH"])
    if not seed_path.exists():
        return 0

    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    count = 0
    for item in payload.get("employees", []):
        employee = Employee(
            employee_id=str(item.get("employee_id", "")).strip(),
            full_name=item.get("full_name") or "Unnamed Employee",
            preferred_name=item.get("preferred_name") or None,
            email=normalize_email(item.get("email")),
            phone=item.get("phone") or None,
            extension=item.get("extension") or None,
            department=item.get("department") or None,
            designation=item.get("designation") or None,
            blood_group=item.get("blood_group") or None,
            fun_fact=item.get("fun_fact") or None,
            photo_path=item.get("photo_path") or None,
            is_active=bool(item.get("is_active", True)),
            serial_no=int(item.get("serial_no", 999)),
        )
        if not employee.employee_id:
            continue
        db.session.add(employee)
        count += 1
    db.session.commit()
    app.logger.info("Seeded %s employees from %s", count, seed_path)
    return count
