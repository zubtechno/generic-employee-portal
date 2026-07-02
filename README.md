# AKASH Employee Portal

A modern, responsive Progressive Web App (PWA) Employee Portal built with Flask, integrating Authentik Single Sign-On (SSO) and featuring a Technology Clearance workflow, Expiration Reminders, and a Technology Issue Tracker.

---

## 🚀 How to Push this Project to GitHub

Since GitHub no longer supports password authentication over HTTPS, you must use a **Personal Access Token (PAT)** or an **SSH Key**. Follow these steps:

1. **Create a GitHub Repository**:
   - Go to [GitHub](https://github.com/) and log in as `zubtechno`.
   - Click **New** to create a new repository.
   - Name it `akash-employee-portal` (leave it empty without initializing with README/gitignore).

2. **Generate a Personal Access Token (PAT)**:
   - Go to **Settings** -> **Developer Settings** -> **Personal Access Tokens** -> **Tokens (classic)**.
   - Click **Generate new token (classic)**.
   - Give it a name, set the expiration, and select the **repo** scope.
   - Copy the generated token (you won't be able to see it again).

3. **Push the Local Code**:
   Open PowerShell/Terminal in the project directory (`c:\Users\abdullah.zubayer\OneDrive - AKASH Digital TV\Documents\Create HRM portal sso with authentik`) and run:
   ```bash
   # Initialize Git (if not already done)
   git init

   # Add files to commit
   git add .
   git commit -m "Initial commit: AKASH Employee Portal"

   # Rename branch to main
   git branch -M main

   # Add the remote origin (replace YOUR_TOKEN with the PAT you generated)
   git remote add origin https://zubtechno:YOUR_TOKEN@github.com/zubtechno/akash-employee-portal.git

   # Push to GitHub
   git push -u origin main
   ```

---

## 🛠️ Customization Guide: Where to Edit for Your Projects

If you want to adapt this portal for other projects or change system configurations, here is a guide on what files to edit:

### 1. Remote Server & SSO Deployment Configs
* **File to edit**: [deploy_remote.py](file:///c:/Users/abdullah.zubayer/OneDrive%20-%20AKASH%20Digital%20TV/Documents/Create%20HRM%20portal%20sso%20with%20authentik/deploy_remote.py)
* **What to change**:
  - `HOST` (Line 10): Target host IP address (`192.168.151.59`).
  - `REDIRECT_URI` (Line 19): Callback URL for authentication redirect.
  - `APP_NAME` (Line 16) & `PROVIDER_NAME` (Line 18): Rebrand the SSO details.

### 2. SMTP & Email Server Settings
* **File to edit**: `.env` (generated dynamically on deploy) or [app/utils.py](file:///c:/Users/abdullah.zubayer/OneDrive%20-%20AKASH%20Digital%20TV/Documents/Create%20HRM%20portal%20sso%20with%20authentik/app/utils.py)
* **What to change**:
  - Update SMTP server IP (`192.168.151.76`), port (`25`), and sender email address (`employee.portal@akashdth.com`) to connect to your local mail server.

### 3. Adding/Modifying Database Models
* **File to edit**: [app/models.py](file:///c:/Users/abdullah.zubayer/OneDrive%20-%20AKASH%20Digital%20TV/Documents/Create%20HRM%20portal%20sso%20with%20authentik/app/models.py)
* **What to change**:
  - Add tables, modify column relations, or customize tracking structures (e.g. Clearance requests, notification schemas).

### 4. Background Services & Expiration Reminders
* **File to edit**: [app/cli.py](file:///c:/Users/abdullah.zubayer/OneDrive%20-%20AKASH%20Digital%20TV/Documents/Create%20HRM%20portal%20sso%20with%20authentik/app/cli.py)
* **What to change**:
  - Default settings, notification intervals (e.g. 60, 45, 30 days prior thresholds), and automatic seed lists for departments/employees.

---

## 📱 Progressive Web App (PWA) Support
The portal has built-in PWA capabilities.
* **Manifest Settings**: [app/static/manifest.json](file:///c:/Users/abdullah.zubayer/OneDrive%20-%20AKASH%20Digital%20TV/Documents/Create%20HRM%20portal%20sso%20with%20authentik/app/static/manifest.json) - custom name, standalone display mode, background colors.
* **Service Worker**: [app/static/js/sw.js](file:///c:/Users/abdullah.zubayer/OneDrive%20-%20AKASH%20Digital%20TV/Documents/Create%20HRM%20portal%20sso%20with%20authentik/app/static/js/sw.js) - caching strategy (Network-First for application routing pages, Cache-First for static assets).
