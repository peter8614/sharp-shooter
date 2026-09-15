import 'package:flutter_test/flutter_test.dart';
import 'package:shot_rater/config/release_configuration.dart';

void main() {
  group('production backend URL validation', () {
    test('accepts a production HTTPS origin with an optional path', () {
      expect(
        productionBackendUrlError('https://api.sharpshooter.app/v1'),
        isNull,
      );
    });

    test('rejects placeholders, local hosts, and insecure URLs', () {
      expect(productionBackendUrlError('https://api.example.com'), isNotNull);
      expect(productionBackendUrlError('https://api.sharpshooter.test'),
          isNotNull);
      expect(
          productionBackendUrlError('http://api.sharpshooter.app'), isNotNull);
      expect(productionBackendUrlError('https://localhost:5000'), isNotNull);
      expect(productionBackendUrlError(''), isNotNull);
    });

    test('rejects query strings and fragments', () {
      expect(
        productionBackendUrlError('https://api.sharpshooter.app?debug=true'),
        isNotNull,
      );
      expect(
        productionBackendUrlError('https://api.sharpshooter.app/#debug'),
        isNotNull,
      );
    });

    test('rejects credentials embedded in the URL', () {
      expect(
        productionBackendUrlError('https://user:secret@api.sharpshooter.app'),
        isNotNull,
      );
    });
  });
}
