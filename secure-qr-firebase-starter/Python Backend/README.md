# Secure QR — Phase 2: ES256 JWS credential prototype

**Scope:** Firebase Authentication ID token verification, approved user checks, room existence check, 30-second ES256 JWT issuance, strict cryptographic JWT validation, admin-only validation test. **Does not grant physical access** and does NOT implement replay prevention, ABAC, device binding, offline access, revocation or audit logging.

## Windows setup

1. Open the folder in VS Code and create an isolated Python environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env`. Set `FIREBASE_PROJECT_ID` to the exact project ID shown in Firebase Project settings (not its display name).
3. Firebase Console > Project settings > Service accounts > Generate new private key. Save the downloaded JSON as `firebase-service-account.json` in this folder. **Never publish or deploy this JSON; it grants server privileges.** You can alternatively configure Google Application Default Credentials. In production prefer workload identity rather than a downloaded key.
4. Generate an EC signing key pair (safe only for this local demo):

   ```powershell
   python generate_keys.py
   ```

5. In Firebase Firestore, ensure you have `users/{firebaseUid}` with `status: "APPROVED"` for your test user, `admins/{adminUid}` for your test admin, and a `rooms/LAB_A` document. All test user accounts must exist in Firebase Authentication. The user role stored in Firestore is NOT currently consulted in issuance, because ABAC is Phase 5.
6. Run unit tests without Firebase credentials:

   ```powershell
   python -m pytest -q
   ```

7. Start backend:

   ```powershell
   python -m uvicorn app.main:app --reload
   ```

8. Visit `http://127.0.0.1:8000/docs`. For `/qr/issue`, click **Authorize** and enter the full Firebase user **ID token** (not your API key, password, UID or the custom QR token). In FastAPI Swagger's bearer authorization popup, paste the Firebase ID token itself. Call `/qr/issue` with `{ "room_id":"LAB_A" }` and copy the issued `token`. To call `/qr/validate`, authorize using an admin user's Firebase ID token and paste the issued QR token in the request body.

## Flutter ID token usage

```dart
import 'package:firebase_auth/firebase_auth.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

Future<String> requestQr() async {
  final user = FirebaseAuth.instance.currentUser;
  if (user == null) throw StateError('Sign in first');
  final idToken = await user.getIdToken();
  final res = await http.post(
    Uri.parse('http://10.0.2.2:8000/qr/issue'),
    headers: {
      'Authorization': 'Bearer $idToken',
      'Content-Type': 'application/json',
    },
    body: jsonEncode({'room_id': 'LAB_A'}),
  );
  if (res.statusCode != 200) throw Exception('QR issue failed: ${res.statusCode}');
  return jsonDecode(res.body)['token'] as String;
}
```

The emulator address `10.0.2.2` is only for Android emulator development on your own PC. Use HTTPS for any remote or real network testing. Do not store the QR token as a long-term credential or expose it in logs.

## Security and next phases

- `/qr/validate` is **administrator-only** and tests signature/claims; it **does not** allow door access. It is not a facility scanner endpoint.
- No replay protection yet: the same valid JWT passes validation repeatedly within its lifetime. Implement atomic `jti` consumption and authenticated verifier identity in Phase 3.
- No biometric bound key or proof of possession yet: a screen-captured token remains usable within its expiry window. Phase 4 adds native hardware-backed signing and verifier challenge protocol design.
- Room existence is not room *authorization*. Phase 5 adds verified role, room, time and bookings.
- Offline verification requires a separately designed verifier, policy snapshots, expiry controls and offline audit sync.
- Never deploy `.env`, EC private key or Firebase service-account JSON to public hosting; don't add them to Git.
- All endpoints currently assume a trusted development environment; before production, add secure hosting, HTTPS, request rate limits, audit logs and proper separation of trusted verifier identity.
