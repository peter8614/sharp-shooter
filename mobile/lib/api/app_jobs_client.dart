import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'api_client.dart';

class AppUploadTicket {
  const AppUploadTicket({required this.jobId, required this.uploadUrl});

  final String jobId;
  final Uri uploadUrl;

  factory AppUploadTicket.fromJson(Map<String, dynamic> json) {
    final jobId = json['job_id'];
    final rawUrl = json['upload_url'];
    final url = rawUrl is String ? Uri.tryParse(rawUrl) : null;
    if (jobId is! String ||
        jobId.isEmpty ||
        url == null ||
        url.scheme != 'https' ||
        url.host.isEmpty ||
        url.userInfo.isNotEmpty) {
      throw const FormatException('Invalid upload ticket.');
    }
    return AppUploadTicket(jobId: jobId, uploadUrl: url);
  }
}

class AppAnalysisJob {
  const AppAnalysisJob({
    required this.jobId,
    required this.status,
    this.result,
    this.error,
  });

  final String jobId;
  final String status;
  final Map<String, dynamic>? result;
  final String? error;

  bool get isComplete => status == 'completed';
  bool get isFailed => status == 'failed';

  factory AppAnalysisJob.fromJson(Map<String, dynamic> json) {
    final jobId = json['job_id'];
    final status = json['status'];
    if (jobId is! String || status is! String) {
      throw const FormatException('Invalid job status.');
    }
    final rawResult = json['result'];
    return AppAnalysisJob(
      jobId: jobId,
      status: status,
      result: rawResult is Map<String, dynamic> ? rawResult : null,
      error: json['error'] is String ? json['error'] as String : null,
    );
  }
}

class AppJobsClient {
  AppJobsClient({
    required String baseUrl,
    required this.accessToken,
    http.Client? client,
    this.requestTimeout = const Duration(seconds: 20),
    this.uploadTimeout = const Duration(minutes: 10),
  })  : _baseUrl = baseUrl.replaceFirst(RegExp(r'/+$'), ''),
        _client = client ?? http.Client();

  final String _baseUrl;
  final Future<String> Function() accessToken;
  final http.Client _client;
  final Duration requestTimeout;
  final Duration uploadTimeout;

  static String contentTypeForPath(String path) {
    final extension = path.split('.').last.toLowerCase();
    return switch (extension) {
      'mp4' => 'video/mp4',
      'mov' => 'video/quicktime',
      'avi' => 'video/x-msvideo',
      'mkv' => 'video/x-matroska',
      _ => throw const ApiException('Unsupported video format.'),
    };
  }

  Future<AppUploadTicket> createJob(String filePath) async {
    final token = await _token();
    final response = await _client
        .post(
          Uri.parse('$_baseUrl/jobs'),
          headers: {
            'Authorization': 'Bearer $token',
            'Content-Type': 'application/json',
          },
          body: jsonEncode({
            'filename': filePath.split(Platform.pathSeparator).last,
            'content_type': contentTypeForPath(filePath),
          }),
        )
        .timeout(requestTimeout);
    return AppUploadTicket.fromJson(_body(response, 201));
  }

  Future<void> uploadVideo(AppUploadTicket ticket, String filePath) async {
    final file = File(filePath);
    final request = http.StreamedRequest('PUT', ticket.uploadUrl)
      ..headers['Content-Type'] = contentTypeForPath(filePath)
      ..contentLength = await file.length();
    final sendFuture = _client.send(request);
    await request.sink.addStream(file.openRead());
    await request.sink.close();
    final streamed = await sendFuture.timeout(uploadTimeout);
    final response =
        await http.Response.fromStream(streamed).timeout(uploadTimeout);
    if (response.statusCode != 200) {
      throw ApiException(
        'Video upload failed (${response.statusCode}). Please retry.',
        statusCode: response.statusCode,
      );
    }
  }

  Future<AppAnalysisJob> getJob(String jobId) async {
    final token = await _token();
    final response = await _client.get(
      Uri.parse('$_baseUrl/jobs/${Uri.encodeComponent(jobId)}'),
      headers: {'Authorization': 'Bearer $token'},
    ).timeout(requestTimeout);
    return AppAnalysisJob.fromJson(_body(response, 200));
  }

  Future<Uri> getVideoUrl(String jobId, String videoKind) async {
    if (videoKind != 'processed' && videoKind != 'reference') {
      throw ArgumentError('Invalid video kind.');
    }
    final token = await _token();
    final response = await _client.get(
      Uri.parse('$_baseUrl/jobs/${Uri.encodeComponent(jobId)}/videos/$videoKind'),
      headers: {'Authorization': 'Bearer $token'},
    ).timeout(requestTimeout);
    final rawUrl = _body(response, 200)['video_url'];
    final url = rawUrl is String ? Uri.tryParse(rawUrl) : null;
    if (url == null ||
        url.scheme != 'https' ||
        url.host.isEmpty ||
        url.userInfo.isNotEmpty) {
      throw const ApiException('The video link was invalid.');
    }
    return url;
  }

  Future<String> _token() async {
    try {
      return await accessToken();
    } catch (_) {
      throw const ApiException(
        'Your session has expired. Please sign in again.',
        statusCode: 401,
        isUnauthorized: true,
      );
    }
  }

  Map<String, dynamic> _body(http.Response response, int expectedStatus) {
    Map<String, dynamic>? json;
    try {
      final decoded = jsonDecode(response.body);
      if (decoded is Map<String, dynamic>) json = decoded;
    } on FormatException {
      // The fallback below avoids surfacing HTML/error pages from infrastructure.
    }
    if (response.statusCode != expectedStatus) {
      final error = json?['error'];
      throw ApiException(
        error is String ? error : 'Request failed (${response.statusCode}).',
        statusCode: response.statusCode,
        isUnauthorized: response.statusCode == 401,
      );
    }
    if (json == null)
      throw const ApiException('The server response was invalid.');
    return json;
  }

  void close() => _client.close();
}
