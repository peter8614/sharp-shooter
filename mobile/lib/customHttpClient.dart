import 'package:http/http.dart' as http;
// This wrapper uses the platform's normal certificate validation. Never add a
// badCertificateCallback here, because it would enable man-in-the-middle attacks.
class CustomHttpClient extends http.BaseClient {
  final http.Client _inner;

  CustomHttpClient() : _inner = http.Client();

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    return _inner.send(request);
  }

  @override
  void close() => _inner.close();
}
