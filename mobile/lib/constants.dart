import 'package:flutter/material.dart';

import 'customHttpClient.dart';

String appName = 'SharpShooter';
Color primaryColor = Color.fromRGBO(22, 69, 69, 1.0);
Color secondaryColor = Color.fromRGBO(220, 140, 49, 1.0);
String collection = 'HoopsVision';
// Supply the production HTTPS endpoint with --dart-define=BACKEND_URL=...
const String backend_Url = String.fromEnvironment(
  'BACKEND_URL',
  defaultValue: 'https://api.example.com',
);
String? user_id;
String? id_token;

// All protected API routes require the token returned by Firebase sign-in.
Map<String, String> authenticatedHeaders({bool json = false}) {
  final token = id_token;
  if (token == null || token.isEmpty) {
    throw StateError('The user is not authenticated.');
  }
  return {
    if (json) 'Content-Type': 'application/json',
    'Authorization': 'Bearer $token',
  };
}

// Create the custom HTTP client
var customHttpClient = CustomHttpClient();
