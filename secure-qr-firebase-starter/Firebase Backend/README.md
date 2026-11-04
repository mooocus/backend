# Secure QR — Firebase Spark registration + administrator dashboard starter

This is a functional **Firebase Authentication + Firestore + Firebase Hosting** user administration prototype. It does **not** deploy FastAPI, PostgreSQL, a cryptographic QR issuer, or a trusted physical door verifier.

## What is included
- Flutter registration and login helper functions (`flutter_snippets/firebase_registration.dart`).
- Firebase-hosted admin login and live user list, approve/reject/suspend, staff/researcher/student role assignment.
- Manage rooms, ABAC policy records, and administrator-issued bookings.
- Audit records for admin changes stored in Firestore using atomic write batches.
- Firestore rules to prohibit self-approval, self-promotion, unauthorized admin access and client-written audit edits.

## Setup
1. Create Firebase project on the free **Spark** plan at https://console.firebase.google.com.
2. Enable Authentication > Sign-in method > Email/Password.
3. Create Cloud Firestore database in production mode. The default database must exist.
4. Project settings > Your apps > Add web app. Copy its Firebase config into `public/firebase-config.js`.
5. Install Node.js, then `npm install -g firebase-tools` and `firebase login`.
6. From the extracted starter directory: `firebase use --add` to select your Firebase project (or `firebase init` if not already initialized).
7. Deploy rules FIRST: `firebase deploy --only firestore:rules`.
8. In Firebase Authentication > Users, add an administrator email/password account. Copy its exact **UID**.
9. In Firestore Console, manually create a collection `admins`, document ID exactly the admin's Auth UID, with a field `createdBy` (string) = `console-bootstrap`. Firestore rules prohibit users creating this marker themselves. Restrict who can access your Firebase Console.
10. Deploy the website: `firebase deploy --only hosting`.
11. Log in at `https://YOUR_PROJECT_ID.web.app` with the **Firebase Authentication** admin account. This does not use your earlier FastAPI `.env` account automatically.
12. Flutter: `flutter pub add firebase_core firebase_auth cloud_firestore` and `dart pub global activate flutterfire_cli`, then `flutterfire configure`, and initialize Firebase in `main.dart`. Integrate the snippet into your screens.

## Firestore collections
- `admins/{uid}`: trusted console-bootstrapped admin marker.
- `users/{authUid}`: name, email, role, status, createdAt, approvedAt, approvedBy.
- `rooms/{roomId}`: name, description, enabled.
- `access_policies/{policyId}`: roomId, allowedRoles, startHour, endHour, bookingRequired, enabled.
- `bookings/{bookingId}`: userId, roomId, startAt, endAt, status.
- `audit_logs/{eventId}`: type, actorUid, targetUid, outcome, details, createdAt.

## Security boundaries / known limitations
- Firebase Authentication authenticates pending users; Firestore rules and trusted access decisions must enforce approval. Do not rely on the login screen alone.
- The admin marker is created in the privileged Firebase console. No self-registration grants admin privileges.
- ABAC policies are stored/configured but **not evaluated as a trusted physical entry decision**. Do not allow a client to unlock a door from this demo.
- Audit logs are immutable to ordinary Firebase clients (admins can append only), but **not tamper-evident and not an independent server-authenticated audit trail**. Console operators retain elevated access. For serious security logs use a trusted service and append-only/tamper-evident storage.
- There is no secure QR signing, JWS replay protection, offline verifier or QR revocation enforcement in this starter. Do not put signing private keys in Flutter/browser/Firestore.
- User registration Auth create and Firestore profile write are not atomic across services. Handle orphaned Auth users when write fails.
- Approvals create atomic admin audit events for dashboard changes. For higher-assurance audit use a server-side authenticated backend.
- Firestore rules check Firebase request timestamps and constrain fields; test these rules in the Firebase Emulator Suite, including unauthorized edits, before real use.
- Cloud Firestore and Firebase Hosting have no-cost quotas; Cloud Functions and Cloud Run require Blaze/billing. See https://firebase.google.com/pricing.
- The rules deliberately keep room/policy reads admin-only for now. Trusted mobile/verifier policy delivery requires a separate secure architecture.
- The role and room hour model uses simple integer hours, and has no timezone/day-of-week or holiday support. Add those in the dedicated access decision service.
- Firebase web SDK `firebaseConfig` is public configuration, not a secret; nevertheless, enable App Check and restrict API key usage where appropriate. Never commit service account credentials.
- You can retain PostgreSQL later for server-side access decisions and high-volume audit processing, but it is not necessary for the included functions.

## Next phase
Implement a trustworthy QR issue/verify API with ES256 JWS, device-held keys, secure clock, revocation, atomic replay tracking, and offline verifier sync. A server-side backend will be needed; Firebase Spark static Hosting cannot replace this.
