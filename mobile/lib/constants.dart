import 'package:flutter/material.dart';

import 'api/api_client.dart';
import 'api/session_store.dart';
import 'config/release_configuration.dart';

const String appName = 'SharpShooter';
const Color primaryColor = Color.fromRGBO(22, 69, 69, 1.0);
const Color secondaryColor = Color.fromRGBO(220, 140, 49, 1.0);
// The canonical release script rejects placeholders before an IPA is built.
const String backendUrl = configuredBackendUrl;

final SessionStore sessionStore = SessionStore();
final ApiClient apiClient = ApiClient(
  baseUrl: backendUrl,
  sessionStore: sessionStore,
);
