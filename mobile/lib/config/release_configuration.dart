const String configuredBackendUrl = String.fromEnvironment(
  'BACKEND_URL',
  defaultValue: 'https://api.example.com',
);

String? cognitoAppConfigurationError({
  required String appApiUrl,
  required String clientId,
  required String issuer,
}) {
  final values = [appApiUrl.trim(), clientId.trim(), issuer.trim()];
  if (values.every((value) => value.isEmpty)) return null;
  if (values.any((value) => value.isEmpty)) {
    return 'APP_API_URL, COGNITO_CLIENT_ID and COGNITO_ISSUER must be set together.';
  }
  final api = Uri.tryParse(appApiUrl);
  final authority = Uri.tryParse(issuer);
  if (api == null ||
      api.scheme != 'https' ||
      api.host.isEmpty ||
      api.path != '/app' ||
      api.userInfo.isNotEmpty ||
      api.hasQuery ||
      api.hasFragment) {
    return 'APP_API_URL must be the HTTPS App API root ending in /app.';
  }
  if (authority == null ||
      authority.scheme != 'https' ||
      authority.host.isEmpty ||
      authority.userInfo.isNotEmpty ||
      authority.hasQuery ||
      authority.hasFragment) {
    return 'COGNITO_ISSUER must be a complete HTTPS issuer URL.';
  }
  return null;
}

String? productionBackendUrlError(String value) {
  final uri = Uri.tryParse(value.trim());
  if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) {
    return 'BACKEND_URL must be a complete HTTPS URL.';
  }
  final host = uri.host.toLowerCase();
  if (host == 'example.com' ||
      host.endsWith('.example.com') ||
      host.endsWith('.example') ||
      host.endsWith('.invalid') ||
      host.endsWith('.test') ||
      host == 'localhost' ||
      host == '127.0.0.1' ||
      host == '::1' ||
      host.endsWith('.localhost')) {
    return 'BACKEND_URL must point to the production API, not a placeholder or local host.';
  }
  if (uri.hasFragment || uri.hasQuery) {
    return 'BACKEND_URL cannot contain a query string or fragment.';
  }
  if (uri.userInfo.isNotEmpty) {
    return 'BACKEND_URL cannot contain embedded credentials.';
  }
  return null;
}
