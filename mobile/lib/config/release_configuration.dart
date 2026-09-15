const String configuredBackendUrl = String.fromEnvironment(
  'BACKEND_URL',
  defaultValue: 'https://api.example.com',
);

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
