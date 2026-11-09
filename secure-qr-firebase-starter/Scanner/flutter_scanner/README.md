# Secure QR Scanner — Android / iOS / Web

A cross-platform Flutter **scanner client** for the existing Secure QR FastAPI backend. The backend remains the *only* authority that may grant room access.

## Included

- Dark scanner interface, camera preview, online status, and green/red decision screen
- Camera QR scanning with `mobile_scanner` for Android, iOS, and Web
- Paste-a-fresh-JWT test mode for devices without a camera
- POST `/scanner/verify` with `X-Scanner-ID`, `X-Scanner-Key`, JSON `{ "token": "..." }`
- Accepts `GRANTED` **only** on HTTP 200 with JSON `decision: "GRANTED"`; otherwise denies
- Backend health check; requests fail closed on offline/timeout/errors
- Scanner ID, backend address, and scanner secret configured at runtime (secret not persisted)

## What this does NOT do

- Does not implement secure offline verification or audit sync. **Offline = DENIED**.
- Does not authenticate device hardware/attest trusted device identity.
- Does not provide physical door actuation.
- Web is a demo/test client only: **a web browser cannot securely retain a shared scanner secret**. Do not use the Web build to control real doors.
- Scanner's displayed gate label is cosmetic; room identification occurs **only server-side** via `scanners/{scannerId}.roomId`.

## Create the full Flutter project

This ZIP contains source files, not pre-generated Flutter platform scaffolding. On your computer with Flutter installed:

```powershell
# From secure-qr-firebase-starter/Scanner
flutter create --project-name secure_qr_scanner --platforms=android,ios,web flutter_scanner
```

Copy these files from the extracted ZIP into `Scanner/flutter_scanner/` (replace generated `lib/main.dart` and `pubspec.yaml`):

```
lib/main.dart
lib/services/scanner_api.dart
pubspec.yaml
analysis_options.yaml
```

Then:

```powershell
cd flutter_scanner
flutter pub get
flutter analyze
flutter run -d edge --dart-define=QR_API_URL=http://127.0.0.1:8000 --dart-define=SCANNER_ID=scanner-001 --dart-define=SCANNER_LABEL="Gate 3 — Main Entrance"
```

**Runtime:** click the Settings (gear) icon and paste the `SCANNER_KEY` provisioned for `scanner-001` in your backend `.env` -> `SCANNER_KEYS_JSON`. It is deliberately *not* supplied via `--dart-define` or embedded in the web bundle.

## Required backend CORS change for Web

In `Python Backend/app/main.py`, adjust your existing CORSMiddleware `allow_headers` to:

```python
allow_headers=[
    "Authorization", "Content-Type", "X-Scanner-ID", "X-Scanner-Key"
],
```

Your existing `allow_origin_regex` already permits local Flutter Web origins on `http://localhost:<port>`.

Restart FastAPI after changing CORS. **Use an explicit HTTPS origin allowlist in production**, not a broad regex.

## Android setup

Open `flutter_scanner/android/app/src/main/AndroidManifest.xml`. Add camera and internet permissions immediately within `<manifest ...>` and outside `<application>`:

```xml
<uses-permission android:name="android.permission.CAMERA" />
<uses-permission android:name="android.permission.INTERNET" />
```

`mobile_scanner` uses the camera and requests runtime permission. Check package requirements (Android minSdk 23 or higher depending on your Flutter environment).

For the **Android emulator only**, FastAPI on your Windows host is `http://10.0.2.2:8000` rather than `127.0.0.1`. If Android blocks debug cleartext HTTP, add to `android/app/src/debug/AndroidManifest.xml` inside `<manifest>`:

```xml
<application android:usesCleartextTraffic="true" />
```

Keep production `https://` endpoints. For a physical Android phone, `10.0.2.2` doesn't refer to your PC; use a reachable HTTPS domain for FastAPI.

## iOS setup

On a Mac with Xcode, edit `flutter_scanner/ios/Runner/Info.plist`. Add inside `<dict>`:

```xml
<key>NSCameraUsageDescription</key>
<string>Scan facility access QR passes.</string>
```

Build/run using Xcode-supported iOS tooling and use an HTTPS backend reachable from the iPhone. iOS builds require a Mac/Xcode.

## Web camera behavior

Web camera access requires HTTPS or `localhost`, browser camera permission, and a camera device. A Windows desktop without a camera can still use **Paste JWT (testing)**. Do not paste production credentials into third-party sites. Hosting on Firebase does not automatically host FastAPI; set `QR_API_URL` to the separately deployed HTTPS API address.

## Firestore scanner assignment

Create/confirm `scanners/scanner-001`:

- `enabled`: **Boolean** `true` (not string `"true"`)
- `roomId`: the real room document ID, e.g. `5aHtm4VejojtDUCfuGMg`

The backend reads this document, checks JWT signature, account approval, ABAC, booking and replay. No room chooser exists in the Flutter scanner.

## Testing

1. Start FastAPI: `py -m uvicorn app.main:app --reload --port 8000`.
2. Start Flutter Scanner, open Settings, enter scanner credentials; status becomes Online if `/health` is reachable.
3. Open your existing user Flutter app and display a fresh signed QR.
4. Scan via camera, or paste the entire three-segment JWT within 30 seconds.
5. Check GRANTED/DENIED based on the backend; reusing a successfully consumed JWT should be denied as replay.

Keep `SCANNER_KEYS_JSON` secrets server-side and out of Git. Never log raw JWTs, scanner secrets or private signing keys. A compromised client with a shared scanner key can impersonate that scanner; a real deployment needs managed device identity and appropriate enrollment.
