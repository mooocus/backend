// Add dependencies: flutter pub add firebase_core firebase_auth cloud_firestore
// Configure: flutterfire configure
// In main(): await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
import 'package:firebase_auth/firebase_auth.dart';
import 'package:cloud_firestore/cloud_firestore.dart';

Future<void> registerForApproval({required String name, required String email, required String password}) async {
  final auth = FirebaseAuth.instance;
  final credential = await auth.createUserWithEmailAndPassword(email: email.trim(), password: password);
  final user = credential.user!;
  try {
    await FirebaseFirestore.instance.collection('users').doc(user.uid).set({
      'name': name.trim(),
      'email': user.email,
      'role': 'USER',
      'status': 'PENDING',
      'createdAt': FieldValue.serverTimestamp(),
      'approvedAt': null,
      'approvedBy': null,
    });
  } finally {
    // If the write fails, this leaves an orphan Auth account. Handle recovery
    // explicitly in production; do not claim that a failed write succeeded.
    await auth.signOut();
  }
}

Future<void> loginWithApproval({required String email, required String password}) async {
  final auth = FirebaseAuth.instance;
  final cred = await auth.signInWithEmailAndPassword(email: email.trim(), password: password);
  try {
    final snapshot = await FirebaseFirestore.instance.collection('users').doc(cred.user!.uid)
        .get(const GetOptions(source: Source.server));
    if (!snapshot.exists || snapshot.data()?['status'] != 'APPROVED') {
      throw StateError('Account not yet approved or is disabled');
    }
    // Navigation only. Critical access must be enforced server-side / by Firestore rules.
  } catch (_) {
    await auth.signOut();
    rethrow;
  }
}
