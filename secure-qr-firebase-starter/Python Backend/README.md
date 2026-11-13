# Secure QR — FastAPI service

Issues short-lived ES256 QR identity passes and decides, for a trusted scanner, whether the holder may enter the room that scanner guards. The service does **not** open any door; scanners only display ACCESS GRANTED or ACCESS DENIED.

## What it does

| Endpoint | Caller | Purpose |
| --- | --- | --- |
| `GET /health` | anyone | Liveness check |
| `POST /qr/issue` | approved user (Firebase ID token) | Returns a 30-second, room-independent ES256 pass: `{token, token_type, expires_in}` |
| `POST /qr/validate` | administrator (Firebase ID token) | Checks signature and claims only; grants nothing |
| `POST /scanner/verify` | scanner (`X-Scanner-ID`, `X-Scanner-Key`) | Verifies the pass, consumes it once, applies the access policy for the scanner's own room, writes an audit record, returns `{decision, reason, room_id, ...}` |

Token: header `typ: facility-identity+jwt`, `kid: issuer-key-v1`; claims `iss, aud, sub (Firebase UID), jti, iat, nbf, exp, token_use=facility_identity, ver=2`. It carries no room and no role.

Scanner decision rules (default deny):

1. The scanner ID and key must match `SCANNER_KEYS_JSON`, and `scanners/{id}` must exist with `enabled: true` and a `roomId`. The room comes only from that record, never from the request.
2. The pass must be valid and unused. Each `jti` is stored once in `used_qr_jtis` (a second scan is denied).
3. The user must be `APPROVED` and the Firebase account not disabled; the room must be enabled.
4. An enabled `access_policies` document must match the room and the user's role and the current hour (`ACCESS_TIME_ZONE`, default `Asia/Singapore`; `startHour <= hour < endHour`). If it has `bookingRequired`, an `APPROVED` booking must cover the current time.
5. Every decision is written to `scanner_access_logs`; if that write fails the service answers 503 and gives no decision.

## Setup (Windows)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python generate_keys.py          # local demo signing keys in ./keys
```

Create `.env` in this folder:

```
FIREBASE_PROJECT_ID=<exact project ID>
GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json
JWT_PRIVATE_KEY_FILE=./keys/ec-private.pem
JWT_PUBLIC_KEY_FILE=./keys/ec-public.pem
QR_ISSUER=secure-qr-demo
QR_AUDIENCE=facility-verifier
QR_KEY_ID=issuer-key-v1
ACCESS_TIME_ZONE=Asia/Singapore
SCANNER_KEYS_JSON={"scanner-001":"replace-with-a-long-random-secret"}
```

Never commit `.env`, the private key or the service-account JSON, and never place them in the dashboard's `public` folder.

Firestore data needed:

- `users/{uid}` with `status: "APPROVED"` and a `role`
- `admins/{uid}` with `createdBy: "console-bootstrap"` and `role: "ADMIN"` (for `/qr/validate`)
- `rooms/{roomId}` (enabled), at least one `access_policies` document for it, and a `scanners/{scannerId}` document `{ enabled: true, roomId: "<roomId>" }` created in the Firestore console

Run the tests (no Firebase credentials needed) and start the service:

```powershell
python -m pytest -q
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`. For `/qr/issue` click **Authorize** and paste a Firebase user **ID token** (not the API key, password or UID).

## Limits

- The scanner shared secret has no device attestation or rate limiting.
- Scans are online only; there is no offline mode.
- Requests refused for a bad scanner ID or key (401/403) are not written to `scanner_access_logs`.
- `used_qr_jtis.expiresAt` is meant for a Firestore TTL policy; add one in the console or the collection grows.
- Development-grade deployment: no App Check, and the signing key is a local PEM file. Use HTTPS and a managed key for anything beyond a demo.
