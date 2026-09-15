import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_models.dart';
import 'session_store.dart';

class ApiException implements Exception {
  const ApiException(
    this.message, {
    this.statusCode,
    this.isUnauthorized = false,
  });

  final String message;
  final int? statusCode;
  final bool isUnauthorized;

  @override
  String toString() => message;
}

typedef UnauthorizedCallback = void Function();

class ApiClient {
  ApiClient({
    required String baseUrl,
    required SessionStore sessionStore,
    http.Client? client,
    this.requestTimeout = const Duration(seconds: 20),
    this.uploadTimeout = const Duration(minutes: 10),
    this.accountDeletionTimeout = const Duration(minutes: 2),
  })  : _baseUrl = baseUrl.replaceFirst(RegExp(r'/+$'), ''),
        _sessionStore = sessionStore,
        _client = client ?? http.Client();

  final String _baseUrl;
  final SessionStore _sessionStore;
  final http.Client _client;
  final Duration requestTimeout;
  final Duration uploadTimeout;
  final Duration accountDeletionTimeout;

  UnauthorizedCallback? onUnauthorized;
  Future<AuthSession>? _refreshInFlight;

  Future<AuthSession> signIn(String email, String password) async {
    final response = await _postJson(
      '/sign_in',
      body: {'username': email, 'password': password},
      authenticated: false,
    );
    final session = _parse(
      response,
      AuthSession.fromJson,
      fallbackMessage: 'The sign-in response could not be read.',
    );
    _sessionStore.setSession(session);
    return session;
  }

  Future<AuthSession> register(String email, String password) async {
    final response = await _postJson(
      '/register',
      body: {'username': email, 'password': password},
      authenticated: false,
    );
    final session = _parse(
      response,
      AuthSession.fromJson,
      fallbackMessage: 'The registration response could not be read.',
    );
    _sessionStore.setSession(session);
    return session;
  }

  Future<UploadJob> uploadVideo(String filePath) async {
    try {
      await _refreshIfNeeded();
      final tokenUsed = _sessionStore.idToken;
      var response = await _sendUpload(filePath);
      if (response.statusCode == 401 && _sessionStore.canRefresh) {
        if (_sessionStore.idToken == tokenUsed) await refreshSession();
        response = await _sendUpload(filePath);
      }
      return _parse(
        response,
        UploadJob.fromJson,
        expectedStatusCodes: const {202},
        fallbackMessage: 'The upload response could not be read.',
      );
    } on TimeoutException {
      throw const ApiException(
          'The upload timed out. Please check your connection and try again.');
    } on ApiException {
      rethrow;
    } catch (_) {
      throw const ApiException(
          'The video could not be uploaded. Please check your connection.');
    }
  }

  Future<AuthSession> refreshSession() {
    final existingRefresh = _refreshInFlight;
    if (existingRefresh != null) return existingRefresh;

    final refreshToken = _sessionStore.refreshToken;
    if (refreshToken == null || refreshToken.isEmpty) {
      _expireSession('Your session has expired. Please sign in again.');
    }
    final sessionRevision = _sessionStore.revision;

    late final Future<AuthSession> refresh;
    refresh = (() async {
      try {
        final response = await _postJson(
          '/refresh_token',
          body: {'refresh_token': refreshToken},
          authenticated: false,
        );
        final session = _parse(
          response,
          AuthSession.fromJson,
          fallbackMessage: 'The refreshed session could not be read.',
        );
        if (_sessionStore.revision != sessionRevision) {
          throw const ApiException(
            'The session changed while it was being refreshed.',
            statusCode: 401,
            isUnauthorized: true,
          );
        }
        _sessionStore.setSession(session);
        return session;
      } finally {
        if (identical(_refreshInFlight, refresh)) {
          _refreshInFlight = null;
        }
      }
    })();
    _refreshInFlight = refresh;
    return refresh;
  }

  Future<AnalysisJob> getJob(String jobId) async {
    final response = await _get('/jobs/${Uri.encodeComponent(jobId)}');
    return _parse(
      response,
      AnalysisJob.fromJson,
      fallbackMessage: 'The job status could not be read.',
    );
  }

  Future<List<AnalysisHistoryItem>> getHistory() async {
    final response = await _postJson('/get_user_history', body: const {});
    final object = _decodeSuccessfulObject(response);
    final history = object['history'];
    if (history is! List) {
      throw const ApiException('The history response could not be read.');
    }

    try {
      return history
          .whereType<Map>()
          .map((item) =>
              AnalysisHistoryItem.fromJson(Map<String, dynamic>.from(item)))
          .toList();
    } on FormatException {
      throw const ApiException('The history response could not be read.');
    }
  }

  Future<Uri> getVideoUrl(String processedVideo) async {
    final response = await _postJson(
      '/get_video',
      body: {'processed_video': processedVideo},
    );
    final object = _decodeSuccessfulObject(response);
    final videoUrl = object['video_url'];
    final uri = videoUrl is String ? Uri.tryParse(videoUrl) : null;
    if (uri == null || !uri.hasScheme) {
      throw const ApiException('The video link could not be read.');
    }
    return uri;
  }

  Future<void> deleteAccount() async {
    final response = await _delete(
      '/account',
      timeout: accountDeletionTimeout,
    );
    final object = _decodeSuccessfulObject(response);
    if (object['status'] != 'deleted') {
      throw const ApiException(
          'The account deletion response could not be read.');
    }
  }

  Future<http.Response> _get(String path) async {
    return _sendAuthenticated(
      (headers) => _client.get(_uri(path), headers: headers),
    );
  }

  Future<http.Response> _delete(
    String path, {
    Duration? timeout,
  }) async {
    return _sendAuthenticated(
      (headers) => _client.delete(_uri(path), headers: headers),
      timeout: timeout,
    );
  }

  Future<http.Response> _postJson(
    String path, {
    required Map<String, dynamic> body,
    bool authenticated = true,
  }) async {
    if (authenticated) {
      return _sendAuthenticated(
        (headers) => _client.post(
          _uri(path),
          headers: headers,
          body: jsonEncode(body),
        ),
        json: true,
      );
    }
    return _sendWithTimeout(
      () => _client.post(
        _uri(path),
        headers: const {'Content-Type': 'application/json'},
        body: jsonEncode(body),
      ),
    );
  }

  Future<http.Response> _sendAuthenticated(
    Future<http.Response> Function(Map<String, String> headers) send, {
    bool json = false,
    Duration? timeout,
  }) async {
    await _refreshIfNeeded();
    final tokenUsed = _sessionStore.idToken;
    var response = await _sendWithTimeout(
      () => send(_authenticatedHeaders(json: json)),
      timeout: timeout,
    );
    if (response.statusCode == 401 && _sessionStore.canRefresh) {
      if (_sessionStore.idToken == tokenUsed) await refreshSession();
      response = await _sendWithTimeout(
        () => send(_authenticatedHeaders(json: json)),
        timeout: timeout,
      );
    }
    return response;
  }

  Future<http.Response> _sendUpload(String filePath) async {
    final request = http.MultipartRequest('POST', _uri('/get_prediction'))
      ..headers.addAll(_authenticatedHeaders())
      ..files.add(await http.MultipartFile.fromPath('video', filePath));
    final streamedResponse = await _client.send(request).timeout(uploadTimeout);
    return http.Response.fromStream(streamedResponse).timeout(uploadTimeout);
  }

  Future<http.Response> _sendWithTimeout(
    Future<http.Response> Function() send, {
    Duration? timeout,
  }) async {
    try {
      return await send().timeout(timeout ?? requestTimeout);
    } on TimeoutException {
      throw const ApiException('The request timed out. Please try again.');
    } on ApiException {
      rethrow;
    } catch (_) {
      throw const ApiException(
          'The server could not be reached. Please check your connection.');
    }
  }

  Future<void> _refreshIfNeeded() async {
    if (_sessionStore.shouldRefresh && _sessionStore.canRefresh) {
      await refreshSession();
    }
  }

  T _parse<T>(
    http.Response response,
    T Function(Map<String, dynamic>) parser, {
    Set<int> expectedStatusCodes = const {200},
    required String fallbackMessage,
  }) {
    final object = _decodeObject(response);
    _throwIfUnsuccessful(response, object, expectedStatusCodes);
    if (object == null) {
      throw ApiException(fallbackMessage, statusCode: response.statusCode);
    }
    try {
      return parser(object);
    } on FormatException {
      throw ApiException(fallbackMessage, statusCode: response.statusCode);
    }
  }

  Map<String, dynamic> _decodeSuccessfulObject(http.Response response) {
    final object = _decodeObject(response);
    _throwIfUnsuccessful(response, object, const {200});
    if (object == null) {
      throw ApiException(
        'The server response could not be read.',
        statusCode: response.statusCode,
      );
    }
    return object;
  }

  void _throwIfUnsuccessful(
    http.Response response,
    Map<String, dynamic>? object,
    Set<int> expectedStatusCodes,
  ) {
    if (expectedStatusCodes.contains(response.statusCode)) return;

    final serverMessage = object?['error'];
    final message = serverMessage is String && serverMessage.isNotEmpty
        ? serverMessage
        : 'The request failed (${response.statusCode}). Please try again.';
    if (response.statusCode == 401) {
      _expireSession(message);
    }
    throw ApiException(message, statusCode: response.statusCode);
  }

  Map<String, dynamic>? _decodeObject(http.Response response) {
    if (response.body.trim().isEmpty) return null;
    try {
      final decoded = jsonDecode(response.body);
      return decoded is Map<String, dynamic> ? decoded : null;
    } on FormatException {
      return null;
    }
  }

  Map<String, String> _authenticatedHeaders({bool json = false}) {
    final token = _sessionStore.idToken;
    if (token == null || token.isEmpty) {
      throw const ApiException(
        'Your session has expired. Please sign in again.',
        statusCode: 401,
        isUnauthorized: true,
      );
    }
    return {
      if (json) 'Content-Type': 'application/json',
      'Authorization': 'Bearer $token',
    };
  }

  Never _expireSession(String message) {
    final hadSession = _sessionStore.clear();
    if (hadSession) onUnauthorized?.call();
    throw ApiException(message, statusCode: 401, isUnauthorized: true);
  }

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  void close() => _client.close();
}
