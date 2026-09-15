import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shot_rater/config/release_configuration.dart';
import 'package:shot_rater/constants.dart';

import 'loginScreen.dart';
import 'splashscreen.dart';

final GlobalKey<NavigatorState> rootNavigatorKey = GlobalKey<NavigatorState>();

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final configurationError = productionBackendUrlError(backendUrl);
  if (kReleaseMode && configurationError != null) {
    throw StateError('Invalid release configuration: $configurationError');
  }
  apiClient.onUnauthorized = () {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      rootNavigatorKey.currentState?.pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const LoginPage()),
        (_) => false,
      );
    });
  };
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    final colorScheme = ColorScheme.fromSeed(
      seedColor: primaryColor,
      primary: primaryColor,
      secondary: secondaryColor,
    );
    return MaterialApp(
      navigatorKey: rootNavigatorKey,
      title: appName,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: colorScheme,
        scaffoldBackgroundColor: colorScheme.surface,
        appBarTheme: AppBarTheme(
          backgroundColor: colorScheme.primary,
          foregroundColor: colorScheme.onPrimary,
          centerTitle: true,
        ),
        inputDecorationTheme: const InputDecorationTheme(
          filled: true,
          border: OutlineInputBorder(),
        ),
      ),
      home: const SplashScreen(),
      debugShowCheckedModeBanner: false,
    );
  }
}
