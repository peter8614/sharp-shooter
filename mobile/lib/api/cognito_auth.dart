import 'package:flutter_appauth/flutter_appauth.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Public mobile client using OAuth authorization-code + PKCE. No IAM keys.
class CognitoAuth {
  CognitoAuth({
    required this.clientId,
    required this.issuer,
    this.redirectUri = 'com.codingminds.shotrater://oauth/callback',
    FlutterAppAuth? appAuth,
    FlutterSecureStorage? storage,
  })  : _appAuth = appAuth ?? FlutterAppAuth(),
        _storage = storage ?? const FlutterSecureStorage();

  final String clientId;
  final String issuer;
  final String redirectUri;
  final FlutterAppAuth _appAuth;
  final FlutterSecureStorage _storage;

  static const _refreshTokenKey = 'cognito_dev_refresh_token';
  String? _accessToken;
  String? _refreshToken;
  DateTime? _expiresAt;

  bool get isSignedIn => _refreshToken != null || _accessToken != null;

  Future<bool> restore() async {
    _refreshToken = await _storage.read(key: _refreshTokenKey);
    if (_refreshToken == null) return false;
    try {
      await accessToken();
      return true;
    } catch (_) {
      await signOut();
      return false;
    }
  }

  Future<void> signIn() async {
    final result = await _appAuth.authorizeAndExchangeCode(
      AuthorizationTokenRequest(
        clientId,
        redirectUri,
        issuer: issuer,
        scopes: const ['openid', 'email'],
      ),
    );
    await _acceptTokens(
      result.accessToken,
      result.refreshToken,
      result.accessTokenExpirationDateTime,
    );
  }

  Future<String> accessToken() async {
    final token = _accessToken;
    final expiry = _expiresAt;
    if (token != null &&
        expiry != null &&
        DateTime.now()
            .toUtc()
            .add(const Duration(minutes: 1))
            .isBefore(expiry)) {
      return token;
    }
    final refreshToken =
        _refreshToken ?? await _storage.read(key: _refreshTokenKey);
    if (refreshToken == null || refreshToken.isEmpty) {
      throw StateError('Please sign in again.');
    }
    final response = await _appAuth.token(
      TokenRequest(
        clientId,
        redirectUri,
        issuer: issuer,
        refreshToken: refreshToken,
        scopes: const ['openid', 'email'],
      ),
    );
    await _acceptTokens(
      response.accessToken,
      response.refreshToken ?? refreshToken,
      response.accessTokenExpirationDateTime,
    );
    return _accessToken!;
  }

  Future<void> _acceptTokens(
    String? accessToken,
    String? refreshToken,
    DateTime? expiresAt,
  ) async {
    if (accessToken == null || accessToken.isEmpty || expiresAt == null) {
      throw StateError('Cognito did not return a usable access token.');
    }
    _accessToken = accessToken;
    _expiresAt = expiresAt.toUtc();
    if (refreshToken != null && refreshToken.isNotEmpty) {
      _refreshToken = refreshToken;
      await _storage.write(key: _refreshTokenKey, value: refreshToken);
    }
  }

  Future<void> signOut() async {
    _accessToken = null;
    _refreshToken = null;
    _expiresAt = null;
    await _storage.delete(key: _refreshTokenKey);
  }
}
