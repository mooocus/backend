# Secure QR Access System — Complete Windows Setup Guide

**For the uploaded `backend-main(3).zip` source**  
**Components:** Python FastAPI backend · Firebase Authentication/Firestore/Hosting admin dashboard · Flutter user app · Flutter QR scanner  
**Target:** Windows 10/11 local development, Microsoft Edge for both Flutter apps

> **Do not copy someone else's `.env`, Firebase service-account JSON, or private signing key.** Create your own configuration and keep secrets private. The original uploaded archive contains sensitive credentials and generated keys; **remove those files before sharing a source ZIP**. If that archive was publicly exposed, revoke/rotate the credentials and keys.

## 0. Locate the project directories

After extracting the uploaded archive, the relevant directories have these paths relative to the extraction location:

```text
<EXTRACTED_FOLDER>/
├── backend-main/
│   └── backend-main/
│       └── secure-qr-firebase-starter/
│           ├── Python Backend/
│           │   ├── app/main.py
│           │   ├── app/qr_crypto.py
│           │   ├── app/scanner_access.py
│           │   ├── generate_keys.py
│           │   └── requirements.txt
│           ├── Firebase Backend/
│           │   ├── firebase.json
│           │   ├── firestore.rules
│           │   └── public/
│           │       ├── app.js
│           │       ├── firebase-config.js
│           │       └── index.html
│           └── Scanner/
│               ├── scanner.py
│               └── flutter_scanner/
└── secure-qr-main/
    └── secure-qr-main/
        └── flutter_app/
```

The `secure-qr-main` folder is the **user** app. `Scanner/flutter_scanner` is the **scanner** app. They are separate Flutter projects.

### Before setting up an extracted copy of this particular ZIP

**The uploaded archive includes existing `.env`, `firebase-service-account.json`, a generated `keys/` directory, a `.venv/`, and Flutter-generated `.dart_tool/` directories.** These should **not** be treated as portable starter files. For a new installation, **first** make a clean working copy, remove those *old copies from that new working copy*, and generate/install your own values using the instructions below. Do **not** delete credentials or private keys from an existing live installation unless you have backups and a planned rotation. A fresh copy of `.env.example` is supplied in this guide kit.

## 1. Install prerequisites (once per computer)

- **Python 3.11+** (Python 3.13 is also supported by this project's current dependencies).
- **Node.js** with npm, for the Firebase CLI.
- **Flutter SDK** installed and on PATH; **Edge** or Chrome for Flutter Web.
- A Google account authorized to create and administer a Firebase project.
- Optional: Android Studio for native Android testing. Native iOS builds require macOS + Xcode.

Verify in PowerShell:

```powershell
python --version
node --version
npm --version
flutter doctor
```

If PowerShell blocks activating the Python virtual environment, use the explicit `.venv\Scripts\python.exe` commands instead of changing your machine's execution policy.

## 2. Create and configure a Firebase project

1. Visit https://console.firebase.google.com/ and **create a Firebase project**, or choose a project you are authorized to administer.
2. Note the **Project ID** (not the friendly display name).
3. Under **Authentication > Sign-in method**, enable **Email/Password**.
4. Under **Firestore Database**, create the **default database**. For this application deploy the supplied Security Rules promptly; do not leave permissive test rules in production.
5. Under **Project settings > Your apps**, register a **Web app** for the administrator dashboard. Copy its Firebase config values (`apiKey`, `authDomain`, `projectId`, `appId`).

**All four components must use the same Firebase project:** the FastAPI `.env`, the dashboard's `firebase-config.js`, the user Flutter app's `firebase_options.dart`, and the Firebase CLI deployment target.

### 2A. Set up the dashboard's Firebase config

Open `Firebase Backend/public/firebase-config.js` and replace its placeholders with the values from the Firebase Console's **Web app** configuration:

```javascript
export const firebaseConfig = {
  apiKey: "YOUR_FIREBASE_WEB_API_KEY",
  authDomain: "YOUR_PROJECT_ID.firebaseapp.com",
  projectId: "YOUR_PROJECT_ID",
  appId: "YOUR_FIREBASE_WEB_APP_ID"
};
```

This **Web config is not a service-account private key**. It is intended for browser applications and is not a substitute for backend credentials.

## 3. Configure and run Python FastAPI

Open a **new PowerShell terminal** in `backend-main/backend-main/secure-qr-firebase-starter/Python Backend`.

### 3A. Create the virtual environment and install packages

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The uploaded `requirements.txt` **already includes `tzdata>=2025.2`**; this fixes the Windows `Asia/Singapore` timezone startup error.

### 3B. Generate backend JWT signing keys

```powershell
.\.venv\Scripts\python.exe generate_keys.py
```

This generates:

```text
Python Backend/keys/ec-private.pem    # PRIVATE — do not share
Python Backend/keys/ec-public.pem     # public verification key
```

Run this **only for a fresh setup**. The script refuses to overwrite existing keys. If you are deliberately replacing an old shared key, plan the rotation; previously issued tokens signed with the old key will no longer verify against the new key.

### 3C. Obtain the Firebase Admin service-account JSON

For local Windows development, the backend uses Firebase Admin SDK credentials.

1. In the **same Firebase project**, go to **Project settings > Service accounts**.
2. Select **Generate new private key** (only if permitted by your project administrator).
3. Save the downloaded JSON securely at `Python Backend/firebase-service-account.json`.
4. **Never** put this JSON into the Flutter app, dashboard `public` folder, or GitHub.

This JSON is **not supplied** with the setup kit. Each authorized developer/deployment must obtain its own credentials.

**Alternative for Google Cloud-hosted deployments:** The source supports Application Default Credentials when `GOOGLE_APPLICATION_CREDENTIALS` is unset. Use a properly permissioned cloud service identity rather than bundling a JSON key. The local steps below assume the JSON file for simplicity.

### 3D. Create `.env` using the provided template

Copy this setup kit's `.env.example` into the `Python Backend` directory, then:

```powershell
Copy-Item .env.example .env
notepad .env
```

Replace `YOUR_PROJECT_ID` and `REPLACE_WITH_OWN_RANDOM_SCANNER_SECRET`. Do not change the key paths if you used the commands above.

Template contents:

```dotenv
FIREBASE_PROJECT_ID=YOUR_PROJECT_ID
GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json
JWT_PRIVATE_KEY_FILE=./keys/ec-private.pem
JWT_PUBLIC_KEY_FILE=./keys/ec-public.pem
QR_ISSUER=secure-qr-demo
QR_AUDIENCE=facility-verifier
QR_KEY_ID=issuer-key-v1
SCANNER_KEYS_JSON={"scanner-001":"REPLACE_WITH_OWN_RANDOM_SCANNER_SECRET"}
ACCESS_TIME_ZONE=Asia/Singapore
```

Generate a random scanner key locally using:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

Paste the output **only** into your local `.env`; the scanner must later use the exact same secret.

### 3E. Test and start FastAPI

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Expected line: `INFO: Application startup complete.`

Open:
- http://127.0.0.1:8000/health — should respond with status `ok`.
- http://127.0.0.1:8000/docs — FastAPI Swagger docs.

**Leave this terminal open** while testing locally. Firebase Hosting does not host FastAPI, and closing this terminal stops the API. For an always-on backend deploy it separately to an appropriate hosted service using HTTPS.

### 3F. What the backend does

The uploaded source provides:

- `POST /qr/issue` — checks Firebase ID token and `users/{uid}.status == "APPROVED"`, then signs a room-independent **30-second ES256 JWT**. This uploaded version **does not require Android Keystore, Apple Secure Enclave, or a device challenge**.
- `POST /scanner/verify` — authenticates scanner credentials, checks token signature/expiry, enforces single-use `jti`, applies room/role/time/booking ABAC, and records scanner decisions.
- `POST /qr/validate` — administrator-only token cryptographic validation, **not** permission to open a door.

## 4. Deploy the Firebase administrator dashboard and rules

Open a **second PowerShell terminal** in `backend-main/backend-main/secure-qr-firebase-starter/Firebase Backend`.

```powershell
npm install -g firebase-tools
firebase login
firebase projects:list
```

Your extracted directory already includes `firebase.json` and `firestore.rules`.

To avoid accidentally deploying to a different Firebase project, specify the project explicitly:

```powershell
firebase deploy --project YOUR_PROJECT_ID --only firestore:rules
```

### 4A. Create the first administrator

1. Firebase Console > **Authentication > Users** > **Add user**. Create an admin email/password account.
2. Copy that account's **Firebase Authentication UID**.
3. Firestore Console > **Start collection** > collection ID `admins`.
4. Create a document with **Document ID = the exact admin UID**.
5. Add fields:

```text
role       (string): "ADMIN"
createdBy  (string): "console-bootstrap"
```

**Both fields matter for this uploaded version:** `firestore.rules` checks `admins/{uid}.role == "ADMIN"`. The admin record must be created by an authorized console administrator; ordinary clients cannot create it.

Now deploy hosting:

```powershell
firebase deploy --project YOUR_PROJECT_ID --only hosting
```

Open the resulting Hosting URL (commonly `https://YOUR_PROJECT_ID.web.app`) and log in using the admin's Firebase Authentication email/password.

> The supplied Firebase Backend README is an earlier starter guide. Its administrator setup mentions only `createdBy`; the actual current `firestore.rules` additionally requires `role: "ADMIN"`. Follow the two-field setup above.

## 5. Configure and run the Flutter user application

The **user app** is in `secure-qr-main/secure-qr-main/flutter_app`. Open a **third PowerShell terminal** there.

### 5A. Check Firebase app configuration

The uploaded source already has `lib/firebase_options.dart`, which is tied to a particular Firebase project. **For your own new Firebase project, regenerate it** instead of using the previous author's Firebase project settings:

```powershell
dart pub global activate flutterfire_cli
flutterfire configure
```

Select the **same Firebase project ID** as Step 2 and choose the platforms you want (at least Web for Edge). Ensure the `flutterfire` executable is on your PATH; if not, follow the CLI's PATH instructions.

The Flutter app already includes Firebase packages in `pubspec.yaml`, so you do not need to add them again.

### 5B. Install Flutter packages and run

```powershell
flutter pub get
flutter analyze
flutter run -d edge --dart-define=QR_API_URL=http://127.0.0.1:8000 --dart-define=ENABLE_BIOMETRIC_TEST_BYPASS=true
```

`ENABLE_BIOMETRIC_TEST_BYPASS=true` is **debug-only Web testing**; it is **not real biometric verification**. Omit this flag when testing actual biometric behavior on supported phones. Do not ship it as a production configuration.

Workflow: register a new account → account initially **PENDING** → approve it in the admin dashboard → sign in → open **Your Access Pass** → see a 30-second signed QR.

The backend terminal should show `POST /qr/issue ... 200 OK`. A real account approval is required; registering alone does not grant access.

## 6. Configure the scanner and room policy

The scanner needs an authenticated Firestore record and an active ABAC policy, even if the user's QR is valid.

### 6A. Create an enabled room and test policy

From the administrator dashboard, create a room named **Lab A**, then create an access policy:

| Property | Development-only example |
|---|---|
| `roomId` | The **Firestore document ID** for Lab A (not its label) |
| `allowedRoles` | Include the test user's actual Firestore `role`, e.g. `USER` |
| `startHour` | Integer `0` |
| `endHour` | Integer `24` |
| `bookingRequired` | Boolean `false` |
| `enabled` | Boolean `true` |

These values permit all-hour testing for the specified role; restore more restrictive policy settings after testing.

### 6B. Register the scanner in Firestore

In Firebase Console > Firestore, create:

```text
scanners/
└── scanner-001
    ├── enabled: true                   # Boolean, NOT string
    └── roomId: "<LAB_A_DOCUMENT_ID>"  # String, exact ID
```

`scanner-001` must also exist inside the backend `.env` JSON as `SCANNER_KEYS_JSON={"scanner-001":"..."}`.

### 6C. Run the Flutter Scanner (Web)

Open a **fourth PowerShell terminal** in `backend-main/backend-main/secure-qr-firebase-starter/Scanner/flutter_scanner`:

```powershell
flutter pub get
flutter analyze
flutter run -d edge --dart-define=QR_API_URL=http://127.0.0.1:8000 --dart-define=SCANNER_ID=scanner-001 --dart-define=SCANNER_LABEL="Lab A Entrance"
```

In the scanner's **Settings** screen enter the scanner secret from your local `.env` and check the backend URL and scanner ID. The scanner secret is **not** passed in the command line.

Use the phone/webcam to scan a fresh user QR within 30 seconds. Alternatively, use **Paste JWT (testing)** if you have securely obtained a fresh full JWT in a local development environment. Never paste an expiry timestamp in place of the full JWT, and don't publish raw JWTs in logs.

**Expected result:** `GRANTED` only if authentication, JWT checks, user approval, ABAC role, room, time and booking conditions all pass. Scanning a consumed JWT again should be denied.

### 6D. Optional Python CLI scanner

The Python CLI scanner is a different program from the Flutter scanner; it needs `requests` (and optionally `opencv-python` for webcam mode). In another terminal inside `Scanner`:

```powershell
py -m pip install requests
$env:SCANNER_KEY = "YOUR_SCANNER_SECRET_FROM_ENV"
py scanner.py --scanner-id scanner-001 --mode keyboard
```

Paste a fresh entire three-segment JWT. For camera mode, install `opencv-python` and run `--mode camera`.

## 7. Test the full flow

1. `GET /health` reports `ok`.
2. Dashboard admin can log in.
3. User signs up and is visible as `PENDING`.
4. Admin approves the user (Firestore `users/{uid}.status` becomes `APPROVED`).
5. User signs in, opens the pass screen, and FastAPI returns `POST /qr/issue 200`.
6. Scanner's Settings show valid backend URL, scanner ID and secret; Firestore `scanners/scanner-001` points to the selected room.
7. First scan within 30 seconds should be `GRANTED` if ABAC permits it.
8. Reuse of the same JWT should be `DENIED` because of the consumed `jti`.
9. Check `scanner_access_logs` in Firestore / dashboard for recorded scan decisions.

**Security and testing limits:** Online verification only; no physical door is opened; Web testing bypasses the client biometric prompt in debug mode; scanner shared keys are not secure physical-device attestation; service-side JWT signing and ABAC are still enforced. Scanner credential failures before the audit handler may not be recorded in `scanner_access_logs`.

## 8. Troubleshooting

| Symptom | Likely issue / action |
|---|---|
| `No time zone found with key Asia/Singapore` | Reinstall packages from current `requirements.txt`; confirm `tzdata` is installed. |
| `Firebase service account file not found` | Put your own private JSON at `Python Backend/firebase-service-account.json` and check `.env`. |
| `The initialized Firebase project does not match FIREBASE_PROJECT_ID` | Ensure service-account JSON, dashboard, Flutter config and `.env` all target the same project. |
| `No issues found` from `flutter analyze`, but QR isn't shown | Check Flutter terminal error, then backend terminal and `/health`. |
| `Hardware-bound QR is available only in native Android and iOS builds` | You're using a different/older Flutter source version; the uploaded user app reviewed here uses `POST /qr/issue` without hardware proof. |
| `POST /qr/issue 401` | Missing, invalid or expired Firebase ID token; check login and Firebase project. |
| `POST /qr/issue 403` | User profile is absent or not `APPROVED`. |
| Scanner `HTTP 401` | Scanner ID/key mismatch between Settings and `.env`. |
| Scanner disabled or room not assigned | Verify `scanners/scanner-001.enabled` is Boolean `true` and `roomId` matches an enabled room. |
| `No matching active access policy` | Check `access_policies` for matching `roomId`, `allowedRoles`, `startHour/endHour`, `enabled`, and booking requirements. |
| Admin role change yields `Missing or insufficient permissions` | **Known issue in the supplied rules:** role-only updates can be blocked because `users/{uid}` update requires `approvedBy` and `approvedAt` to match the current administrator/time for every update. A targeted rules change is needed for role-only edits; don't loosen all user updates. |
| Browser CORS error | Run both Web apps against local FastAPI `http://127.0.0.1:8000`; backend currently allows localhost/127.0.0.1 origins and scanner headers. Add exact hosted HTTPS origins to production CORS settings. |
| Scanner offline | Scanner fails closed; no grant without a valid backend decision. |

## 9. Safe distribution checklist (before GitHub/ZIP)

Do **not** distribute:

```text
Python Backend/.env
Python Backend/firebase-service-account.json
Python Backend/keys/ec-private.pem
Python Backend/keys/ec-public.pem  # not secret, but generate per installation in this workflow
Python Backend/.venv/
**/__pycache__/
**/.dart_tool/
**/build/
**/node_modules/
**/.firebase/
```

Also inspect the repo for any other copies of credentials or `.env` files, and do not include Flutter debug logs containing raw QR JWTs. `*.gitignore` does **not** remove files that were already committed or included in a manually created ZIP. If secrets were committed, remove them from history and rotate them. Use the provided `.env.example` in the repo instead.

## 10. Useful official setup references

- Firebase Admin SDK and service-account authentication: https://firebase.google.com/docs/admin/setup
- Firebase CLI / Hosting & Rules deployment: https://firebase.google.com/docs/cli
- FlutterFire CLI setup: https://firebase.google.com/docs/flutter/setup
- Flutter installation: https://docs.flutter.dev/get-started/install

---

**Setup summary:** Create Firebase project → configure dashboard Web app → create a new private Admin SDK credential locally → install Python dependencies & generate signing keys → create `.env` → start FastAPI → deploy Firestore rules & dashboard → bootstrap admin → regenerate user Flutter Firebase config → run user app → create room/policy/scanner → run scanner → scan a 30-second JWT.
