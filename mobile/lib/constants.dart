import 'package:flutter/material.dart';

import 'api/api_client.dart';
import 'api/session_store.dart';

const String appName = 'SharpShooter';
const Color primaryColor = Color.fromRGBO(22, 69, 69, 1.0);
const Color secondaryColor = Color.fromRGBO(220, 140, 49, 1.0);
// Supply the production HTTPS endpoint with --dart-define=BACKEND_URL=...
const String backendUrl = String.fromEnvironment(
  'BACKEND_URL',
  defaultValue: 'https://api.example.com',
);

final SessionStore sessionStore = SessionStore();
final ApiClient apiClient = ApiClient(
  baseUrl: backendUrl,
  sessionStore: sessionStore,
);
