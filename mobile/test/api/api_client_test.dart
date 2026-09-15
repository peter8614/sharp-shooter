import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shot_rater/api/api_client.dart';
import 'package:shot_rater/api/api_models.dart';
import 'package:shot_rater/api/session_store.dart';

void main() {
  group('ApiClient compatibility contract', () {
    test('sign in preserves the existing backend request and response fields',
        () async {
      final store = SessionStore();
      final client = ApiClient(
        baseUrl: 'https://api.example.test',
        sessionStore: store,
        client: MockClient((request) async {
          expect(request.method, 'POST');
          expect(request.url.path, '/sign_in');
          expect(jsonDecode(request.body), {
            'username': 'player@example.com',
            'password': 'secret',
          });
          return http.Response(
            jsonEncode({
              'user_id': 'user-1',
              'idToken': 'token-1',
              'refreshToken': 'refresh-1',
              'expiresIn': '3600',
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }),
      );

      final session = await client.signIn('player@example.com', 'secret');

      expect(session.userId, 'user-1');
      expect(store.idToken, 'token-1');
      expect(store.refreshToken, 'refresh-1');
      expect(session.shouldRefresh, isFalse);
    });

    test('legacy authentication responses remain valid without refresh fields',
        () {
      final session = AuthSession.fromJson({
        'user_id': 'legacy-user',
        'idToken': 'legacy-token',
      });

      expect(session.idToken, 'legacy-token');
      expect(session.canRefresh, isFalse);
      expect(session.expiresAt, isNull);
    });

    test('job status uses the existing authenticated jobs endpoint', () async {
      final store = SessionStore()
        ..setSession(const AuthSession(userId: 'user-1', idToken: 'token-1'));
      final client = ApiClient(
        baseUrl: 'https://api.example.test/',
        sessionStore: store,
        client: MockClient((request) async {
          expect(request.method, 'GET');
          expect(request.url.path, '/jobs/job-1');
          expect(request.headers['Authorization'], 'Bearer token-1');
          return http.Response(
            jsonEncode({'status': 'complete', 'analysis_id': 'analysis-1'}),
            200,
          );
        }),
      );

      final job = await client.getJob('job-1');

      expect(job.isComplete, isTrue);
      expect(job.analysisId, 'analysis-1');
    });

    test('video upload preserves the multipart endpoint and 202 contract',
        () async {
      final store = SessionStore()
        ..setSession(const AuthSession(userId: 'user-1', idToken: 'token-1'));
      final client = ApiClient(
        baseUrl: 'https://api.example.test',
        sessionStore: store,
        client: MockClient((request) async {
          expect(request.method, 'POST');
          expect(request.url.path, '/get_prediction');
          expect(request.headers['Authorization'], 'Bearer token-1');
          expect(request.headers['content-type'],
              startsWith('multipart/form-data'));
          return http.Response(
            jsonEncode({'job_id': 'job-1', 'status': 'queued'}),
            202,
          );
        }),
      );
      final temporaryDirectory =
          await Directory.systemTemp.createTemp('sharp-shooter-test-');
      final video =
          File('${temporaryDirectory.path}${Platform.pathSeparator}shot.mp4');
      await video.writeAsBytes(const [0, 1, 2, 3]);

      try {
        final job = await client.uploadVideo(video.path);
        expect(job.jobId, 'job-1');
        expect(job.status, 'queued');
      } finally {
        await temporaryDirectory.delete(recursive: true);
      }
    });

    test('history parsing tolerates optional and unknown fields', () async {
      final store = SessionStore()
        ..setSession(const AuthSession(userId: 'user-1', idToken: 'token-1'));
      final client = ApiClient(
        baseUrl: 'https://api.example.test',
        sessionStore: store,
        client: MockClient((request) async {
          return http.Response(
            jsonEncode({
              'history': [
                {
                  'analysis_id': 'analysis-1',
                  'form_classification': 'good',
                  'trajectory_classification': 'bad',
                  'processed_video': 'user-1/videos/video.mp4',
                  'timestamp': '2026-08-22T12:30:00+00:00',
                  'future_field': true,
                },
                {'analysis_id': 'analysis-2', 'timestamp': null},
              ],
            }),
            200,
          );
        }),
      );

      final history = await client.getHistory();

      expect(history, hasLength(2));
      expect(history.first.formClassification, ShotClassification.good);
      expect(history.last.timestamp, isNull);
      expect(history.last.formClassification, ShotClassification.unknown);
    });

    test('401 refreshes the token once and retries the protected request',
        () async {
      final store = SessionStore()
        ..setSession(AuthSession(
          userId: 'user-1',
          idToken: 'expired-token',
          refreshToken: 'refresh-1',
          expiresAt: DateTime.now().toUtc().add(const Duration(minutes: 5)),
        ));
      var historyRequests = 0;
      var refreshRequests = 0;
      final client = ApiClient(
        baseUrl: 'https://api.example.test',
        sessionStore: store,
        client: MockClient((request) async {
          if (request.url.path == '/refresh_token') {
            refreshRequests++;
            expect(jsonDecode(request.body), {'refresh_token': 'refresh-1'});
            return http.Response(
              jsonEncode({
                'user_id': 'user-1',
                'idToken': 'new-token',
                'refreshToken': 'refresh-2',
                'expiresIn': '3600',
              }),
              200,
            );
          }
          historyRequests++;
          if (request.headers['Authorization'] == 'Bearer expired-token') {
            return http.Response(jsonEncode({'error': 'Token expired'}), 401);
          }
          expect(request.headers['Authorization'], 'Bearer new-token');
          return http.Response(jsonEncode({'history': []}), 200);
        }),
      );

      final history = await client.getHistory();

      expect(history, isEmpty);
      expect(historyRequests, 2);
      expect(refreshRequests, 1);
      expect(store.idToken, 'new-token');
      expect(store.refreshToken, 'refresh-2');
    });

    test('an expiring session refreshes before a protected request', () async {
      final store = SessionStore()
        ..setSession(AuthSession(
          userId: 'user-1',
          idToken: 'almost-expired-token',
          refreshToken: 'refresh-1',
          expiresAt: DateTime.now().toUtc().add(const Duration(seconds: 10)),
        ));
      final paths = <String>[];
      final client = ApiClient(
        baseUrl: 'https://api.example.test',
        sessionStore: store,
        client: MockClient((request) async {
          paths.add(request.url.path);
          if (request.url.path == '/refresh_token') {
            return http.Response(
              jsonEncode({
                'user_id': 'user-1',
                'idToken': 'new-token',
                'refreshToken': 'refresh-2',
                'expiresIn': '3600',
              }),
              200,
            );
          }
          expect(request.headers['Authorization'], 'Bearer new-token');
          return http.Response(jsonEncode({'history': []}), 200);
        }),
      );

      await client.getHistory();

      expect(paths, ['/refresh_token', '/get_user_history']);
    });

    test('401 clears the session and notifies the app once', () async {
      final store = SessionStore()
        ..setSession(
            const AuthSession(userId: 'user-1', idToken: 'expired-token'));
      final client = ApiClient(
        baseUrl: 'https://api.example.test',
        sessionStore: store,
        client: MockClient((request) async {
          return http.Response(jsonEncode({'error': 'Token expired'}), 401);
        }),
      );
      var notifications = 0;
      client.onUnauthorized = () => notifications++;

      await expectLater(
        client.getHistory(),
        throwsA(
          isA<ApiException>()
              .having((error) => error.isUnauthorized, 'isUnauthorized', isTrue)
              .having((error) => error.message, 'message', 'Token expired'),
        ),
      );

      expect(store.isAuthenticated, isFalse);
      expect(notifications, 1);
    });
  });
}
