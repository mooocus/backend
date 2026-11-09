import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import 'services/scanner_api.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const SecureQrScannerApp());
}

class SecureQrScannerApp extends StatelessWidget {
  const SecureQrScannerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Secure QR · Scanner',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0B1428),
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF4285FF),
          brightness: Brightness.dark,
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: const Color(0xFF17243A),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
          contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 16),
        ),
      ),
      home: const ScannerHome(),
    );
  }
}

class ScannerHome extends StatefulWidget {
  const ScannerHome({super.key});

  @override
  State<ScannerHome> createState() => _ScannerHomeState();
}

class _ScannerHomeState extends State<ScannerHome> with WidgetsBindingObserver {
  static const _blue = Color(0xFF3983FF);
  static const _muted = Color(0xFF9EADC7);
  static const _panel = Color(0xFF1B293F);

  final _api = const ScannerApi();
  final _camera = MobileScannerController(
    detectionSpeed: DetectionSpeed.noDuplicates,
    formats: const [BarcodeFormat.qrCode],
    autoStart: false,
  );

  ScannerConfig _config = const ScannerConfig(
    backendUrl: String.fromEnvironment(
      'QR_API_URL',
      defaultValue: 'http://127.0.0.1:8000',
    ),
    scannerId: String.fromEnvironment('SCANNER_ID', defaultValue: 'scanner-001'),
    scannerKey: '',
    gateLabel: String.fromEnvironment(
      'SCANNER_LABEL',
      defaultValue: 'Gate 3 — Main Entrance',
    ),
  );

  Timer? _heartbeat;
  bool _online = false;
  bool _busy = false;
  final bool _cameraEnabled = true;
  bool _disposed = false;
  ScanOutcome? _result;
  DateTime? _checkedAt;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _checkBackend();
    _heartbeat = Timer.periodic(const Duration(seconds: 12), (_) => _checkBackend());
    WidgetsBinding.instance.addPostFrameCallback((_) => _startCamera());
  }

  Future<void> _startCamera() async {
    if (_disposed || !_cameraEnabled || _result != null) return;
    try {
      await _camera.start();
    } catch (_) {
      // Camera errors are rendered by MobileScanner.errorBuilder.
    }
  }

  Future<void> _stopCamera() async {
    try {
      await _camera.stop();
    } catch (_) {}
  }

  Future<void> _checkBackend() async {
    final config = _config;
    final connected = await _api.health(config);
    if (!mounted || _disposed || config.backendUrl != _config.backendUrl) return;
    setState(() {
      _online = connected;
      _checkedAt = DateTime.now();
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _checkBackend();
      _startCamera();
    } else if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden) {
      _stopCamera();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _heartbeat?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    _camera.dispose();
    super.dispose();
  }

  void _detect(BarcodeCapture capture) {
    if (_busy || _result != null) return;
    for (final barcode in capture.barcodes) {
      final value = barcode.rawValue;
      if (value != null && value.isNotEmpty) {
        _verify(value);
        break;
      }
    }
  }

  Future<void> _verify(String token) async {
    if (_busy || _result != null || !mounted) return;
    setState(() => _busy = true);
    await _stopCamera();

    final outcome = await _api.verify(config: _config, jwt: token.trim());
    if (!mounted) return;
    setState(() {
      _busy = false;
      _result = outcome;
      if (outcome.kind == ScanResultKind.unavailable) _online = false;
    });
    // Never write the raw JWT or scanner secret to logs.
  }

  Future<void> _newScan() async {
    setState(() => _result = null);
    await _checkBackend();
    await _startCamera();
  }

  Future<void> _manualInput() async {
    if (_busy) return;
    await _stopCamera();
    if (!mounted) return;
    final controller = TextEditingController();
    final token = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Paste JWT for testing'),
        content: SizedBox(
          width: 500,
          child: TextField(
            controller: controller,
            autofocus: true,
            maxLines: 4,
            decoration: const InputDecoration(
              hintText: 'eyJ... . eyJ... . signature',
              helperText: 'A QR JWT normally expires after 30 seconds.',
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, controller.text),
            child: const Text('Verify'),
          ),
        ],
      ),
    );
    // The dialog has returned; the text controller is no longer required.
    controller.dispose();
    if (!mounted) return;
    if (token != null && token.trim().isNotEmpty) {
      await _verify(token);
    } else {
      await _startCamera();
    }
  }

  Future<void> _settings() async {
    await _stopCamera();
    if (!mounted) return;
    final endpoint = TextEditingController(text: _config.backendUrl);
    final id = TextEditingController(text: _config.scannerId);
    final label = TextEditingController(text: _config.gateLabel);
    final key = TextEditingController(text: _config.scannerKey);
    String? error;
    bool obscure = true;

    final changed = await showDialog<ScannerConfig>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, update) => AlertDialog(
          title: const Text('Scanner configuration'),
          content: SizedBox(
            width: 520,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Provision scanner credentials on the device. '
                    'This example stores the secret in memory only.',
                    style: TextStyle(color: _muted, fontSize: 13),
                  ),
                  const SizedBox(height: 16),
                  TextField(controller: label, decoration: const InputDecoration(labelText: 'Display label')),
                  const SizedBox(height: 12),
                  TextField(controller: endpoint, decoration: const InputDecoration(labelText: 'FastAPI URL')),
                  const SizedBox(height: 12),
                  TextField(controller: id, decoration: const InputDecoration(labelText: 'Scanner ID')),
                  const SizedBox(height: 12),
                  TextField(
                    controller: key,
                    obscureText: obscure,
                    decoration: InputDecoration(
                      labelText: 'Scanner secret',
                      suffixIcon: IconButton(
                        icon: Icon(obscure ? Icons.visibility : Icons.visibility_off),
                        onPressed: () => update(() => obscure = !obscure),
                      ),
                    ),
                  ),
                  if (kIsWeb) ...[
                    const SizedBox(height: 12),
                    const Text(
                      'WEB DEMO ONLY: a browser cannot safely hold a persistent scanner secret. '
                      'Use an authenticated managed scanner device for real door control.',
                      style: TextStyle(color: Color(0xFFFFC16B), fontSize: 12),
                    ),
                  ],
                  if (error != null) ...[
                    const SizedBox(height: 12),
                    Text(error!, style: const TextStyle(color: Color(0xFFFF7979))),
                  ],
                ],
              ),
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cancel')),
            FilledButton(
              onPressed: () {
                if (!ScannerApi.isAllowedUrl(endpoint.text)) {
                  update(() => error = 'Use HTTPS; only local debug HTTP is permitted.');
                  return;
                }
                if (id.text.trim().isEmpty || key.text.isEmpty) {
                  update(() => error = 'Enter scanner ID and secret.');
                  return;
                }
                Navigator.pop(
                  dialogContext,
                  ScannerConfig(
                    backendUrl: endpoint.text.trim(),
                    scannerId: id.text.trim(),
                    scannerKey: key.text,
                    gateLabel: label.text.trim(),
                  ),
                );
              },
              child: const Text('Save'),
            ),
          ],
        ),
      ),
    );
    // Delay disposal until after dialog closing animation to avoid controllers
    // being referenced while the dialog is transitioning off-screen.
    await Future<void>.delayed(const Duration(milliseconds: 200));
    endpoint.dispose();
    id.dispose();
    label.dispose();
    key.dispose();
    if (!mounted) return;
    if (changed != null) {
      setState(() => _config = changed);
      await _checkBackend();
    }
    await _startCamera();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 510),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(22, 18, 22, 22),
              child: _result == null ? _scannerView() : _resultView(_result!),
            ),
          ),
        ),
      ),
    );
  }

  Widget _scannerView() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _config.gateLabel.isEmpty ? 'QR Access Scanner' : _config.gateLabel,
                    style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Container(
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color: _online ? const Color(0xFF16B66A) : const Color(0xFFF0A12C),
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _online ? 'Online · Connected to backend' : 'Offline · All access denied',
                          style: const TextStyle(fontSize: 12, color: _muted),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            IconButton.filledTonal(
              tooltip: 'Scanner settings',
              onPressed: _settings,
              icon: const Icon(Icons.settings_outlined),
            ),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(20),
                color: _online ? const Color(0xFF086B46) : const Color(0xFF8A520A),
              ),
              child: Text(
                _online ? 'READY' : 'OFFLINE',
                style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800),
              ),
            ),
          ],
        ),
        const SizedBox(height: 26),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(20),
            child: Container(
              color: _panel,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  if (_cameraEnabled)
                    MobileScanner(
                      controller: _camera,
                      useAppLifecycleState: false,
                      onDetect: _detect,
                      errorBuilder: (context, error) => Center(
                        child: Padding(
                          padding: const EdgeInsets.all(20),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(Icons.videocam_off_outlined, size: 43, color: _muted),
                              const SizedBox(height: 12),
                              const Text('Camera unavailable'),
                              const SizedBox(height: 8),
                              Text(
                                'Grant camera permission, use a device with a camera, '
                                'or paste a test JWT. (${error.errorCode.name})',
                                textAlign: TextAlign.center,
                                style: const TextStyle(fontSize: 12, color: _muted),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  if (_busy)
                    Container(
                      color: const Color(0xC8000000),
                      child: const Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            CircularProgressIndicator(color: _blue),
                            SizedBox(height: 16),
                            Text('Checking access policy…'),
                          ],
                        ),
                      ),
                    ),
                  IgnorePointer(
                    child: CustomPaint(
                      painter: _CornerPainter(),
                      child: const SizedBox.expand(),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 20),
        const Text(
          'Present your QR pass to the camera',
          textAlign: TextAlign.center,
          style: TextStyle(fontWeight: FontWeight.w600, fontSize: 16),
        ),
        const SizedBox(height: 13),
        Text('Scanner ID: ${_config.scannerId}', style: const TextStyle(color: _muted, fontSize: 12)),
        const SizedBox(height: 5),
        Text(
          _config.scannerKey.isEmpty
              ? 'Configure scanner secret using the settings icon'
              : _checkedAt == null
                  ? 'Checking backend status…'
                  : _online
                      ? 'Awaiting scan…'
                      : 'Backend unavailable — fail closed',
          style: TextStyle(
            color: _config.scannerKey.isEmpty ? const Color(0xFFFFC16B) : _muted,
            fontSize: 12,
          ),
        ),
        const SizedBox(height: 15),
        OutlinedButton.icon(
          onPressed: _busy ? null : _manualInput,
          icon: const Icon(Icons.keyboard_outlined),
          label: const Text('Paste JWT (testing)'),
        ),
        if (kIsWeb)
          const Padding(
            padding: EdgeInsets.only(top: 8),
            child: Text(
              'Web demonstration only · Camera requires HTTPS or localhost',
              textAlign: TextAlign.center,
              style: TextStyle(color: _muted, fontSize: 11),
            ),
          ),
      ],
    );
  }

  Widget _resultView(ScanOutcome outcome) {
    final success = outcome.kind == ScanResultKind.granted;
    final bg = success ? const Color(0xFF0E9E52) : const Color(0xFFD92327);
    return Container(
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(22)),
      child: Padding(
        padding: const EdgeInsets.all(25),
        child: Column(
          children: [
            const SizedBox(height: 10),
            Text(_config.gateLabel, textAlign: TextAlign.center, style: const TextStyle(fontSize: 15)),
            const Spacer(),
            Container(
              width: 140,
              height: 140,
              decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
              child: Icon(success ? Icons.check_rounded : Icons.close_rounded, size: 92, color: bg),
            ),
            const SizedBox(height: 35),
            Text(
              success ? 'ACCESS GRANTED' : 'ACCESS DENIED',
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w900, color: Colors.white),
            ),
            const SizedBox(height: 14),
            Text(
              outcome.reason,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 16, color: Colors.white),
            ),
            if (outcome.kind == ScanResultKind.unavailable) ...[
              const SizedBox(height: 12),
              const Text(
                'No offline access grants are supported.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.white70, fontSize: 13),
              ),
            ],
            const Spacer(),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: Colors.white,
                foregroundColor: const Color(0xFF16243A),
                minimumSize: const Size.fromHeight(52),
              ),
              onPressed: _newScan,
              icon: const Icon(Icons.qr_code_scanner),
              label: const Text('Scan next pass'),
            ),
            const SizedBox(height: 12),
          ],
        ),
      ),
    );
  }
}

class _CornerPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFF418AFF)
      ..strokeWidth = 4
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    const inset = 24.0;
    const length = 22.0;
    final left = inset;
    final right = size.width - inset;
    final top = inset;
    final bottom = size.height - inset;
    final paths = [
      [Offset(left + length, top), Offset(left, top), Offset(left, top + length)],
      [Offset(right - length, top), Offset(right, top), Offset(right, top + length)],
      [Offset(left + length, bottom), Offset(left, bottom), Offset(left, bottom - length)],
      [Offset(right - length, bottom), Offset(right, bottom), Offset(right, bottom - length)],
    ];
    for (final points in paths) {
      final path = Path()..moveTo(points[0].dx, points[0].dy);
      for (final point in points.skip(1)) {
        path.lineTo(point.dx, point.dy);
      }
      canvas.drawPath(path, paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
