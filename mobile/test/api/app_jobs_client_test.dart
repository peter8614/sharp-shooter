import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shot_rater/api/app_jobs_client.dart';
import 'package:shot_rater/api/api_client.dart';

void main() {
  test('App flow uses JWT for create/get and no credentials on S3 PUT',
      () async {
    final temporaryDirectory =
        await Directory.systemTemp.createTemp('shot-app-');
    final video =
        File('${temporaryDirectory.path}${Platform.pathSeparator}shot.mov');
    await video.writeAsBytes([1, 2, 3]);
    final calls = <String>[];
    final client = AppJobsClient(
      baseUrl: 'https://api.example.test/app',
      accessToken: () async => 'access-token',
      client: MockClient((request) async {
        calls.add('${request.method} ${request.url.path}');
        if (request.method == 'POST') {
          expect(request.headers['Authorization'], 'Bearer access-token');
          expect(jsonDecode(request.body)['content_type'], 'video/quicktime');
          return http.Response(
              jsonEncode({
                'job_id': 'job-1',
                'upload_url': 'https://uploads.example.test/shot',
              }),
              201);
        }
        if (request.method == 'PUT') {
          expect(request.headers['Authorization'], isNull);
          expect(request.headers['Content-Type'], 'video/quicktime');
          expect(request.bodyBytes, [1, 2, 3]);
          return http.Response('', 200);
        }
        expect(request.headers['Authorization'], 'Bearer access-token');
        return http.Response(
            jsonEncode({
              'job_id': 'job-1',
              'status': 'completed',
              'result': {'form_classification': 'good'},
            }),
            200);
      }),
    );

    try {
      final ticket = await client.createJob(video.path);
      await client.uploadVideo(ticket, video.path);
      final result = await client.getJob(ticket.jobId);
      expect(result.isComplete, isTrue);
      expect(result.result?['form_classification'], 'good');
      expect(calls, ['POST /app/jobs', 'PUT /shot', 'GET /app/jobs/job-1']);
    } finally {
      client.close();
      await temporaryDirectory.delete(recursive: true);
    }
  });

  test('rejects non-HTTPS presigned upload URL', () {
    expect(
      () => AppUploadTicket.fromJson({
        'job_id': 'job-1',
        'upload_url': 'http://uploads.example.test/shot',
      }),
      throwsFormatException,
    );
  });

  test('identifies failed jobs without assuming legacy complete state', () {
    final job = AppAnalysisJob.fromJson({
      'job_id': 'job-1',
      'status': 'failed',
      'error': 'Video processing failed.',
    });
    expect(job.isFailed, isTrue);
    expect(job.isComplete, isFalse);
  });

  test('video download URL is fetched with JWT and must use HTTPS', () async {
    final client = AppJobsClient(
      baseUrl: 'https://api.example.test/app',
      accessToken: () async => 'access-token',
      client: MockClient((request) async {
        expect(request.url.path, '/app/jobs/job-1/videos/processed');
        expect(request.headers['Authorization'], 'Bearer access-token');
        return http.Response(jsonEncode({
          'video_url': 'https://private.example.test/results/job-1/shot.mp4',
          'expires_in': 300,
        }), 200);
      }),
    );
    try {
      final url = await client.getVideoUrl('job-1', 'processed');
      expect(url.scheme, 'https');
      expect(url.path, '/results/job-1/shot.mp4');
    } finally {
      client.close();
    }
  });

  test('expired Cognito session is reported as unauthorized', () async {
    final client = AppJobsClient(
      baseUrl: 'https://api.example.test/app',
      accessToken: () async => throw StateError('expired'),
      client: MockClient((_) async => throw StateError('should not send')),
    );
    try {
      await expectLater(
        client.getJob('job-1'),
        throwsA(isA<ApiException>().having(
          (error) => error.isUnauthorized,
          'isUnauthorized',
          isTrue,
        )),
      );
    } finally {
      client.close();
    }
  });
}
