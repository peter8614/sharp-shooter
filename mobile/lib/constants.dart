import 'package:flutter/material.dart';

import 'api/api_client.dart';
import 'api/app_jobs_client.dart';
import 'api/cognito_auth.dart';
import 'api/session_store.dart';
import 'config/release_configuration.dart';

const String appName = 'SharpShooter';
const Color primaryColor = Color.fromRGBO(22, 69, 69, 1.0);
const Color secondaryColor = Color.fromRGBO(220, 140, 49, 1.0);
// The canonical release script rejects placeholders before an IPA is built.
const String backendUrl = configuredBackendUrl;

const String appApiUrl = String.fromEnvironment('APP_API_URL');
const String cognitoClientId = String.fromEnvironment('COGNITO_CLIENT_ID');
const String cognitoIssuer = String.fromEnvironment('COGNITO_ISSUER');
const bool useCognitoAppApi =
    appApiUrl != '' && cognitoClientId != '' && cognitoIssuer != '';

final CognitoAuth cognitoAuth = CognitoAuth(
  clientId: cognitoClientId,
  issuer: cognitoIssuer,
);
final AppJobsClient appJobsClient = AppJobsClient(
  baseUrl: appApiUrl,
  accessToken: cognitoAuth.accessToken,
);

final SessionStore sessionStore = SessionStore();
final ApiClient apiClient = ApiClient(
  baseUrl: backendUrl,
  sessionStore: sessionStore,
);
