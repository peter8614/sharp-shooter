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

  group('Cognito App configuration', () {
    test('allows the legacy-only fallback when no App values are set', () {
      expect(
          cognitoAppConfigurationError(
            appApiUrl: '',
            clientId: '',
            issuer: '',
          ),
          isNull);
    });

    test('requires the App values together', () {
      expect(
          cognitoAppConfigurationError(
            appApiUrl: 'https://api.example.com/app',
            clientId: '',
            issuer: 'https://cognito-idp.us-east-1.amazonaws.com/pool',
          ),
          isNotNull);
    });

    test('accepts a complete HTTPS App configuration', () {
      expect(
          cognitoAppConfigurationError(
            appApiUrl: 'https://api.example.com/app',
            clientId: 'public-client',
            issuer: 'https://cognito-idp.us-east-1.amazonaws.com/pool',
          ),
          isNull);
    });

    test('rejects insecure API and issuer URLs', () {
      expect(
          cognitoAppConfigurationError(
            appApiUrl: 'http://api.example.com/app',
            clientId: 'public-client',
            issuer: 'https://cognito-idp.us-east-1.amazonaws.com/pool',
          ),
          isNotNull);
      expect(
          cognitoAppConfigurationError(
            appApiUrl: 'https://api.example.com/app',
            clientId: 'public-client',
            issuer: 'http://cognito-idp.us-east-1.amazonaws.com/pool',
          ),
          isNotNull);
    });
  });
}
