import json
import re
import secrets
from pathlib import Path

from flask import current_app
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename


ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "bmp"}


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def normalize_email(value):
    value = clean_text(value).lower()
    return value or None


def normalize_groups(raw_groups):
    if not raw_groups:
        return []
    if isinstance(raw_groups, str):
        return [raw_groups]
    groups = []
    for group in raw_groups:
        if isinstance(group, dict):
            name = group.get("name") or group.get("slug") or group.get("pk")
        else:
            name = str(group)
        if name:
            groups.append(clean_text(name))
    return groups


def is_admin_identity(email, groups, config):
    email = (email or "").strip().lower()
    admin_emails = {item.lower() for item in config.get("ADMIN_EMAILS", [])}
    admin_groups = {item.lower() for item in config.get("ADMIN_GROUPS", [])}
    group_names = {item.lower() for item in groups}
    return email in admin_emails or bool(group_names & admin_groups)


def serialize_groups(groups):
    return json.dumps(normalize_groups(groups), ensure_ascii=False)


def allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def save_employee_photo(file_storage, employee):
    if not file_storage or not file_storage.filename:
        return employee.photo_path
    if not allowed_image(file_storage.filename):
        raise ValueError("Use a JPG, PNG, WEBP, or BMP image.")

    upload_root = Path(current_app.config["UPLOAD_FOLDER"])
    profile_dir = Path(current_app.config["PROFILE_UPLOAD_SUBDIR"])
    profile_dir.mkdir(parents=True, exist_ok=True)

    try:
        image = Image.open(file_storage.stream)
        image.load()
    except UnidentifiedImageError as exc:
        raise ValueError("The uploaded file is not a readable image.") from exc

    image.thumbnail(current_app.config["PHOTO_MAX_SIZE"], Image.Resampling.LANCZOS)
    if image.mode in {"RGBA", "LA", "P"}:
        background = Image.new("RGB", image.size, (255, 255, 255))
        if image.mode == "P":
            image = image.convert("RGBA")
        background.paste(image, mask=image.split()[-1] if image.mode in {"RGBA", "LA"} else None)
        image = background
    else:
        image = image.convert("RGB")

    employee_key = secure_filename(employee.employee_id or "employee") or "employee"
    original_key = secure_filename(Path(file_storage.filename).stem) or "photo"
    filename = f"{employee_key}_{original_key}_{secrets.token_hex(6)}.jpg"
    destination = profile_dir / filename
    image.save(destination, "JPEG", quality=88, optimize=True)

    return f"uploads/{destination.relative_to(upload_root).as_posix()}"


def photo_static_path(employee):
    return employee.photo_path or "img/avatar.svg"


def send_email(to_addresses, subject, body_text):
    """Sends a plain text email to the recipients list using configured SMTP server."""
    import smtplib
    from email.mime.text import MIMEText
    
    server_host = current_app.config.get("MAIL_SERVER", "192.168.151.76")
    server_port = current_app.config.get("MAIL_PORT", 25)
    sender = current_app.config.get("MAIL_DEFAULT_SENDER", "employee.portal@akashdth.com")
    
    if isinstance(to_addresses, str):
        to_addresses = [to_addresses]
    
    # Filter empty or invalid emails
    valid_recipients = [r.strip() for r in to_addresses if r and "@" in r]
    if not valid_recipients:
        return False
        
    msg = MIMEText(body_text)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = ", ".join(valid_recipients)
    
    try:
        with smtplib.SMTP(server_host, server_port, timeout=5) as server:
            # No authentication or encryption is configured/required based on instructions
            server.sendmail(sender, valid_recipients, msg.as_string())
        return True
    except Exception as e:
        # Silently log errors or print to stderr so it doesn't break the request flow
        import sys
        print(f"SMTP Email Send Failed: {e}", file=sys.stderr)
        return False
