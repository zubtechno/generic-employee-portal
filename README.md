# Employee Portal

A modern, responsive Progressive Web App (PWA) Employee Portal built with Flask, integrating Authentik Single Sign-On (SSO) and featuring a Technology Clearance workflow, Expiration Reminders, and a Technology Issue Tracker.

---

## 🛠️ Customization Guide: Where to Edit for Your Projects

If you want to adapt this portal for other projects or change system configurations, here is a guide on what files to edit:

### 1. Remote Server & SSO Deployment Configs
* **File to edit**: [deploy_remote.py](file:///c:/Users/user/OneDrive%20-%20%20Digital%20TV/Documents/Create%20HRM%20portal%20sso%20with%20authentik/deploy_remote.py)
* **What to change**:
  - `HOST` (Line 10): Target host IP address (`192.168.151.59`).
  - `REDIRECT_URI` (Line 19): Callback URL for authentication redirect.
  - `APP_NAME` (Line 16) & `PROVIDER_NAME` (Line 18): Rebrand the SSO details.

### 2. SMTP & Email Server Settings
* **File to edit**: `.env` (generated dynamically on deploy) or [app/utils.py](file:///c:/Users/user/OneDrive%20-%20%20Digital%20TV/Documents/Create%20HRM%20portal%20sso%20with%20authentik/app/utils.py)
* **What to change**:
  - Update SMTP server IP (`192.168.151.76`), port (`25`), and sender email address (`employee.portal@dth.com`) to connect to your local mail server.

### 3. Adding/Modifying Database Models
* **File to edit**: [app/models.py](file:///c:/Users/user/OneDrive%20-%20%20Digital%20TV/Documents/Create%20HRM%20portal%20sso%20with%20authentik/app/models.py)
* **What to change**:
  - Add tables, modify column relations, or customize tracking structures (e.g. Clearance requests, notification schemas).

### 4. Background Services & Expiration Reminders
* **File to edit**: [app/cli.py](file:///c:/Users/user/OneDrive%20-%20%20Digital%20TV/Documents/Create%20HRM%20portal%20sso%20with%20authentik/app/cli.py)
* **What to change**:
  - Default settings, notification intervals (e.g. 60, 45, 30 days prior thresholds), and automatic seed lists for departments/employees.

---

## 📱 Progressive Web App (PWA) Support
The portal has built-in PWA capabilities.
* **Manifest Settings**: [app/static/manifest.json](file:///c:/Users/user/OneDrive%20-%20%20Digital%20TV/Documents/Create%20HRM%20portal%20sso%20with%20authentik/app/static/manifest.json) - custom name, standalone display mode, background colors.
* **Service Worker**: [app/static/js/sw.js](file:///c:/Users/user/OneDrive%20-%20%20Digital%20TV/Documents/Create%20HRM%20portal%20sso%20with%20authentik/app/static/js/sw.js) - caching strategy (Network-First for application routing pages, Cache-First for static assets).
