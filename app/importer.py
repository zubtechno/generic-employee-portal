import argparse
import html
import json
import re
import shutil
from pathlib import Path


TAG_RE = re.compile(r"<[^>]+>")
BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
TABLE_RE = re.compile(r'<div id="con\d+">\s*<table\b.*?</table>', re.IGNORECASE | re.DOTALL)
ROW_RE = re.compile(r'<tr\b[^>]*bgcolor="#E2E3E4"[^>]*>(.*?)</tr>', re.IGNORECASE | re.DOTALL)
TD_RE = re.compile(r"<td\b[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
IMG_RE = re.compile(r'<img\b[^>]*src="([^"]+)"', re.IGNORECASE)
EMP_ID_RE = re.compile(r"Emp\.\s*ID:\s*([A-Za-z0-9_-]+)", re.IGNORECASE)
DEPT_RE = re.compile(r"<h3>(.*?)</h3>", re.IGNORECASE | re.DOTALL)


def strip_tags(fragment, separator=" "):
    fragment = BR_RE.sub("\n", fragment)
    text = TAG_RE.sub(separator, fragment)
    text = html.unescape(text).replace("\xa0", " ")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def plain(fragment):
    return re.sub(r"\s+", " ", strip_tags(fragment)).strip()


def parse_department(table_html):
    match = DEPT_RE.search(table_html)
    if not match:
        return ""
    heading = plain(match.group(1))
    return re.sub(r"\(\s*\d+\s*\)\s*$", "", heading).strip()


def parse_contact(fragment):
    lines = [line.strip() for line in strip_tags(fragment).splitlines() if line.strip()]
    email = next((line for line in lines if "@" in line), "")
    phone = ""
    extension = ""
    for line in lines:
        if "@" in line:
            continue
        digits = re.sub(r"\D", "", line)
        if not digits:
            continue
        if not phone:
            phone = line
        elif not extension:
            extension = line
    if phone and len(re.sub(r"\D", "", phone)) <= 5 and not extension:
        extension = phone
        phone = ""
    return phone, extension, email


def parse_details(fragment):
    lines = [line.strip() for line in strip_tags(fragment).splitlines() if line.strip()]
    employee_id = ""
    for line in lines:
        match = EMP_ID_RE.search(line)
        if match:
            employee_id = match.group(1).strip()
            break
    usable = [line for line in lines if not EMP_ID_RE.search(line)]
    full_name = usable[0] if usable else ""
    preferred_name = usable[1] if len(usable) > 1 else ""
    blood_group = usable[2] if len(usable) > 2 else ""
    return full_name, preferred_name, blood_group, employee_id


def resolve_asset(src, assets_dir):
    filename = Path(src.replace("\\", "/")).name
    return assets_dir / filename if filename else None


def parse_hrm_html(html_path):
    html_path = Path(html_path)
    content = html_path.read_text(encoding="utf-8", errors="ignore")
    employees = []

    for table_match in TABLE_RE.finditer(content):
        table_html = table_match.group(0)
        department = parse_department(table_html)
        for row_match in ROW_RE.finditer(table_html):
            tds = TD_RE.findall(row_match.group(1))
            if len(tds) < 7:
                continue
            full_name, preferred_name, blood_group, employee_id = parse_details(tds[2])
            if not employee_id or not full_name:
                continue
            phone, extension, email = parse_contact(tds[4])
            photo_match = IMG_RE.search(tds[1])
            qr_match = IMG_RE.search(tds[6])
            employees.append(
                {
                    "employee_id": employee_id,
                    "full_name": full_name,
                    "preferred_name": preferred_name,
                    "blood_group": blood_group,
                    "department": department,
                    "designation": plain(tds[3]),
                    "phone": phone,
                    "extension": extension,
                    "email": email.lower(),
                    "fun_fact": plain(tds[5]),
                    "photo_source": photo_match.group(1) if photo_match else "",
                    "qr_source": qr_match.group(1) if qr_match else "",
                    "is_active": True,
                }
            )
    return employees


def copy_imported_photos(employees, assets_dir, destination_dir):
    assets_dir = Path(assets_dir)
    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for employee in employees:
        source_ref = employee.get("photo_source")
        if not source_ref:
            continue
        source = resolve_asset(source_ref, assets_dir)
        if not source or not source.exists():
            continue
        suffix = source.suffix.lower() or ".jpg"
        destination_name = f"{employee['employee_id']}_pic{suffix}"
        destination = destination_dir / destination_name
        shutil.copy2(source, destination)
        employee["photo_path"] = f"uploads/imported/{destination_name}"
        copied += 1
    return copied


def write_seed_json(employees, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for employee in employees:
        employee.pop("photo_source", None)
        employee.pop("qr_source", None)
    payload = {"employees": employees}
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Parse the saved HRM portal export.")
    parser.add_argument("--html", required=True, help="Path to Beximco Communications.html")
    parser.add_argument("--assets", help="Path to Beximco Communications_files")
    parser.add_argument("--copy-to", help="Directory to copy employee photos into")
    parser.add_argument("--out", required=True, help="Seed JSON output path")
    args = parser.parse_args()

    employees = parse_hrm_html(args.html)
    copied = 0
    if args.assets and args.copy_to:
        copied = copy_imported_photos(employees, args.assets, args.copy_to)
    write_seed_json(employees, args.out)
    print(f"Parsed {len(employees)} employees, copied {copied} photos")


if __name__ == "__main__":
    main()
