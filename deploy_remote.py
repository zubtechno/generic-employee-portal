import os
import zipfile
import secrets
import paramiko
import json
import io
import time

# Remote Server Settings
HOST = "192.168.151.59"
USER = "azubayer"
PASS = "Zub012%%"
REMOTE_DIR = "/home/azubayer/hrm-portal"

# SSO Settings
APP_NAME = "Employee Portal"
APP_SLUG = "employee-portal"
PROVIDER_NAME = "Employee Portal Provider"
REDIRECT_URI = "https://empdetails.company.com/auth/callback"

def run_ssh_command(client, command, run_as_sudo=False):
    if run_as_sudo:
        command = f"echo '{PASS}' | sudo -S {command}"
    
    stdin, stdout, stderr = client.exec_command(command)
    exit_status = stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='ignore').strip()
    err = stderr.read().decode('utf-8', errors='ignore').strip()
    return exit_status, out, err

def main():
    print(f"Connecting to {HOST}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=HOST, username=USER, password=PASS, timeout=10)
    print("Connected successfully.")

    # 1. Find Authentik Server Container
    print("Finding Authentik container on host...")
    status, stdout, stderr = run_ssh_command(client, "docker ps --filter name=authentik-server --format '{{.Names}}'", run_as_sudo=True)
    
    container_name = ""
    if status == 0 and stdout:
        container_name = stdout.splitlines()[0].strip()
    else:
        # Fallback search
        status, stdout, stderr = run_ssh_command(client, "docker ps --filter name=authentik --format '{{.Names}}'", run_as_sudo=True)
        if status == 0 and stdout:
            # Prefer server or worker, look for one that looks like server
            containers = [c.strip() for c in stdout.splitlines()]
            for c in containers:
                if "server" in c:
                    container_name = c
                    break
            if not container_name:
                container_name = containers[0]

    if not container_name:
        print("[-] Could not automatically find running Authentik container. Please ensure Authentik is running.")
        client.close()
        return

    print(f"[+] Found Authentik container: {container_name}")

    # 2. Run django-shell script inside Authentik to create/fetch OIDC Provider and Application
    print("Configuring Authentik OIDC via internal Django Shell...")
    django_script = f"""
import json
from authentik.providers.oauth2.models import OAuth2Provider, RedirectURI, RedirectURIMatchingMode, RedirectURIType, GrantType, ScopeMapping
from authentik.core.models import Application, User, Group
from authentik.flows.models import Flow
from authentik.crypto.models import CertificateKeyPair
import secrets

# Find default authorization and invalidation flows
auth_flow = Flow.objects.filter(slug__icontains='authorization').first()
inval_flow = Flow.objects.filter(slug__icontains='invalidation').first()

if not auth_flow:
    auth_flow = Flow.objects.get(slug='default-provider-authorization-explicit-consent')
if not inval_flow:
    inval_flow = Flow.objects.filter(slug='default-invalidation-flow').first() or Flow.objects.first()

# Find signing key
keypair = CertificateKeyPair.objects.filter(name__icontains="self-signed").first() or CertificateKeyPair.objects.first()

uri = RedirectURI(
    matching_mode=RedirectURIMatchingMode.STRICT,
    url="{REDIRECT_URI}",
    redirect_uri_type=RedirectURIType.AUTHORIZATION
)

provider, created = OAuth2Provider.objects.get_or_create(
    name="{PROVIDER_NAME}",
    defaults={{
        "client_type": "confidential",
        "client_id": secrets.token_hex(20),
        "client_secret": secrets.token_hex(40),
        "authorization_flow": auth_flow,
        "invalidation_flow": inval_flow,
        "redirect_uris": [uri],
        "grant_types": [GrantType.AUTHORIZATION_CODE, GrantType.REFRESH_TOKEN],
        "signing_key": keypair
    }}
)

# Ensure default scope mappings exist
email_map, _ = ScopeMapping.objects.get_or_create(
    scope_name="email",
    defaults={{
        "name": "HRM Email Scope",
        "description": "HRM Email Scope",
        "expression": "return {{ 'email': request.user.email, 'email_verified': True }}"
    }}
)

profile_map, _ = ScopeMapping.objects.get_or_create(
    scope_name="profile",
    defaults={{
        "name": "HRM Profile Scope",
        "description": "HRM Profile Scope",
        "expression": "return {{\\n  'name': request.user.name,\\n  'given_name': request.user.name,\\n  'preferred_username': request.user.username,\\n  'nickname': request.user.username\\n}}"
    }}
)

groups_map, _ = ScopeMapping.objects.get_or_create(
    scope_name="groups",
    defaults={{
        "name": "HRM Groups Scope",
        "description": "HRM Groups Scope",
        "expression": "return {{\\n  'groups': [group.name for group in request.user.ak_groups.all()]\\n}}"
    }}
)

# Bind the mappings to the provider
provider.property_mappings.add(email_map, profile_map, groups_map)

if not created:
    # Ensure redirect URIs, grant types, and signing key are correct
    provider.redirect_uris = [uri]
    provider.grant_types = [GrantType.AUTHORIZATION_CODE, GrantType.REFRESH_TOKEN]
    provider.signing_key = keypair

provider.save()

app, app_created = Application.objects.get_or_create(
    slug="{APP_SLUG}",
    defaults={{
        "name": "{APP_NAME}",
        "provider": provider,
        "meta_icon": "https://empdetails.company.com/static/img/icon-192.png"
    }}
)

if not app_created:
    app.name = "{APP_NAME}"
    app.provider = provider
    app.meta_icon = "https://empdetails.company.com/static/img/icon-192.png"
    app.save()

# Create/Update Bexcom Super Admin in Authentik
ak_user, ak_created = User.objects.get_or_create(
    username="bexcom.admin",
    defaults={{
        "name": "Bexcom Admin",
        "email": "bexcom.admin@akashdth.com",
        "is_active": True
    }}
)
ak_user.set_password("3Exc0mD1h!t")
ak_user.save()

# Add to authentik Admins group
admin_group = Group.objects.filter(name="authentik Admins").first()
if admin_group:
    admin_group.users.add(ak_user)


result = {{
    "client_id": provider.client_id,
    "client_secret": provider.client_secret,
    "provider_created": created,
    "app_created": app_created,
    "superadmin_created": ak_created
}}
print("JSON_START" + json.dumps(result) + "JSON_END")
"""
    # Run django script inside container by writing sudo password first, then django script
    django_cmd = f"sudo -S docker exec -i {container_name} ak shell"
    stdin, stdout, stderr = client.exec_command(django_cmd)
    stdin.write(PASS + "\n")
    stdin.write(django_script)
    stdin.channel.shutdown_write()
    
    exit_status = stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='ignore').strip()
    err = stderr.read().decode('utf-8', errors='ignore').strip()
    
    if exit_status != 0:
        print(f"[-] Django shell command failed. Stderr: {err}")
        client.close()
        return

    # Extract JSON results
    if "JSON_START" not in out:
        print(f"[-] Could not read JSON block from container output: {out}")
        client.close()
        return

    json_str = out.split("JSON_START")[1].split("JSON_END")[0].strip()
    oidc_info = json.loads(json_str)
    print("[+] Authentik OIDC configured successfully:")
    print(f"    Client ID: {oidc_info['client_id']}")
    print(f"    Client Secret: [HIDDEN]")

    # 3. Create .env file content locally
    print("Generating local .env file...")
    env_content = f"""SECRET_KEY={secrets.token_hex(32)}

COMPANY_NAME=AKASH Digital TV
PORTAL_NAME=HRM Portal

OIDC_CLIENT_ID={oidc_info['client_id']}
OIDC_CLIENT_SECRET={oidc_info['client_secret']}
OIDC_DISCOVERY_URL=https://sso.akashdth.com/application/o/hrm-portal/.well-known/openid-configuration
OIDC_SCOPE=openid email profile groups
OIDC_LOGOUT_URL=

ADMIN_GROUPS=HRM Admins,hrm-admins
ADMIN_EMAILS=abdullah.zubayer@akashdth.com,bexcom.admin@akashdth.com

SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=Lax
TRUST_PROXY=true

AUTO_SEED=true
DEV_LOGIN_ENABLED=false
"""
    with open(".env", "w", encoding="utf-8") as f:
        f.write(env_content)
    print("[+] Generated .env file.")

    # 4. Modify docker-compose.yml to map port 8082:8000
    print("Updating docker-compose.yml to expose port 8082...")
    with open("docker-compose.yml", "r", encoding="utf-8") as f:
        compose_content = f.read()
    
    # Replace ports mapping
    updated_compose = compose_content.replace('"8080:8000"', '"8082:8000"')
    with open("docker-compose.yml", "w", encoding="utf-8") as f:
        f.write(updated_compose)
    print("[+] Exposing port 8082 in docker-compose.yml.")

    # 5. Zip local directory excluding virtualenv, cache, database file
    print("Zipping local project files...")
    zip_path = "hrm-portal.zip"
    exclude_dirs = {"venv", ".git", "__pycache__", ".gemini", "data"}
    exclude_files = {zip_path, "deploy_remote.py", "deploy_remote.pyc"}

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk("."):
            # Exclude specified directories in-place
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                if file in exclude_files or file.endswith(".pyc") or file.endswith(".sqlite") or file.endswith(".log"):
                    continue
                file_path = os.path.join(root, file)
                archive_name = os.path.relpath(file_path, ".")
                zipf.write(file_path, archive_name)
    print(f"[+] Zipped package as {zip_path}.")

    # 6. Upload zip to server
    print(f"Uploading zip package to remote server {HOST}...")
    sftp = client.open_sftp()
    
    # Create remote directory if not exists
    try:
        sftp.mkdir(REMOTE_DIR)
    except IOError:
        pass # Already exists
        
    sftp.put(zip_path, f"{REMOTE_DIR}/hrm-portal.zip")
    sftp.close()
    print("[+] Uploaded hrm-portal.zip.")

    # 7. Unzip and run docker compose on remote server
    print("Extracting and building application on remote host...")
    commands = [
        "apt-get update",
        "apt-get install -y unzip",
        f"unzip -o {REMOTE_DIR}/hrm-portal.zip -d {REMOTE_DIR}",
        f"rm {REMOTE_DIR}/hrm-portal.zip",
        f"sh -c 'cd {REMOTE_DIR} && docker compose down'",
        f"sh -c 'cd {REMOTE_DIR} && docker compose up -d --build'"
    ]
    
    for cmd in commands:
        print(f"Running: {cmd} ...")
        status, stdout, stderr = run_ssh_command(client, cmd, run_as_sudo=True)
        if status != 0:
            print(f"[-] Command failed: {cmd}\nStdout: {stdout}\nStderr: {stderr}")
            client.close()
            return
            
    print("[+] Docker containers started successfully!")
    
    # 8. Check health
    time.sleep(3)
    status, stdout, stderr = run_ssh_command(client, "docker ps --filter name=hrm", run_as_sudo=True)
    print("\n--- Running Containers Status ---")
    print(stdout)
    
    print("\n[+] Success! Your HRM Portal has been deployed successfully!")
    print(f"    Local URL: http://{HOST}:8082")
    print("    External URL: https://empdetails.akashdth.com")
    
    # Clean up local zip
    if os.path.exists(zip_path):
        os.remove(zip_path)
    
    client.close()

if __name__ == "__main__":
    main()
