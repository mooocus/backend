import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

class ScannerConfig {
  const ScannerConfig({
    required this.backendUrl,
    required this.scannerId,
    required this.scannerKey,
    required this.gateLabel,
  });

  final String backendUrl;
  final String scannerId;
  final String scannerKey;
  final String gateLabel;

  ScannerConfig copyWith({
    String? backendUrl,
    String? scannerId,
    String? scannerKey,
    String? gateLabel,
  }) => ScannerConfig(
        backendUrl: backendUrl ?? this.backendUrl,
        scannerId: scannerId ?? this.scannerId,
        scannerKey: scannerKey ?? this.scannerKey,
        gateLabel: gateLabel ?? this.gateLabel,
      );
}

enum ScanResultKind { granted, denied, unavailable }

class ScanOutcome {
  const ScanOutcome({
    required this.kind,
    required this.reason,
    this.roomId,
    this.policyId,
  });

  final ScanResultKind kind;
  final String reason;
  final String? roomId;
  final String? policyId;
}

class ScannerApi {
  const ScannerApi();

  static bool isAllowedUrl(String value) {
    final uri = Uri.tryParse(value.trim());
    if (uri == null || !uri.hasAuthority || uri.userInfo.isNotEmpty) {
      return false;
    }
    if (uri.scheme == 'https') return true;
    return kDebugMode &&
        uri.scheme == 'http' &&
        uri.port == 8000 &&
        {'localhost', '127.0.0.1', '10.0.2.2'}.contains(uri.host);
  }

  Uri _endpoint(ScannerConfig config, String path) {
    if (!isAllowedUrl(config.backendUrl)) {
      throw const FormatException(
        'Use an HTTPS backend. Debug HTTP is limited to local development.',
      );
    }
    return Uri.parse('${config.backendUrl.trim().replaceFirst(RegExp(r"/+$"), "")}$path');
  }

  Future<bool> health(ScannerConfig config) async {
    try {
      final response = await http
          .get(_endpoint(config, '/health'))
          .timeout(const Duration(seconds: 4));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<ScanOutcome> verify({
    required ScannerConfig config,
    required String jwt,
  }) async {
    if (config.scannerId.trim().isEmpty || config.scannerKey.isEmpty) {
      return const ScanOutcome(
        kind: ScanResultKind.unavailable,
        reason: 'Scanner credentials are not configured.',
      );
    }
    if (jwt.length > 4096 || jwt.split('.').length != 3) {
      return const ScanOutcome(
        kind: ScanResultKind.denied,
        reason: 'The scanned QR is not a valid JWT format.',
      );
    }

    try {
      final response = await http.post(
        _endpoint(config, '/scanner/verify'),
        headers: {
          'Content-Type': 'application/json',
          'X-Scanner-ID': config.scannerId.trim(),
          'X-Scanner-Key': config.scannerKey,
        },
        body: jsonEncode({'token': jwt}),
      ).timeout(const Duration(seconds: 10));

      Map<String, dynamic>? data;
      try {
        final decoded = jsonDecode(response.body);
        if (decoded is Map<String, dynamic>) data = decoded;
      } catch (_) {
        // Do not trust an unparseable response as an access grant.
      }

      if (response.statusCode == 200) {
        if (data?['decision'] == 'GRANTED') {
          return ScanOutcome(
            kind: ScanResultKind.granted,
            reason: (data?['reason'] as String?) ?? 'Access policy satisfied',
            roomId: data?['room_id'] is String ? data!['room_id'] as String : null,
            policyId: data?['policy_id'] is String ? data!['policy_id'] as String : null,
          );
        }
        return ScanOutcome(
          kind: ScanResultKind.denied,
          reason: (data?['reason'] as String?) ?? 'Access not authorized',
        );
      }

      if (response.statusCode == 401) {
        return const ScanOutcome(
          kind: ScanResultKind.unavailable,
          reason: 'Scanner authentication failed. Check its ID and secret.',
        );
      }
      if (response.statusCode == 403) {
        return const ScanOutcome(
          kind: ScanResultKind.unavailable,
          reason: 'Scanner is disabled or has no authorized room assignment.',
        );
      }
      if (response.statusCode == 503 || response.statusCode >= 500) {
        return const ScanOutcome(
          kind: ScanResultKind.unavailable,
          reason: 'Verification service unavailable. Access denied.',
        );
      }
      return ScanOutcome(
        kind: ScanResultKind.denied,
        reason: 'Verification rejected (HTTP ${response.statusCode}).',
      );
    } catch (_) {
      return const ScanOutcome(
        kind: ScanResultKind.unavailable,
        reason: 'Cannot reach verification backend. Access denied.',
      );
    }
  }
}
