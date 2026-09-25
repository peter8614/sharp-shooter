import 'package:flutter/material.dart';

import 'constants.dart';
import 'loginScreen.dart';

Future<void> signOut(BuildContext context) async {
  if (useCognitoAppApi) {
    await cognitoAuth.signOut();
  }
  sessionStore.clear();
  if (!context.mounted) return;
  Navigator.of(context, rootNavigator: true).pushAndRemoveUntil(
    MaterialPageRoute(builder: (_) => const LoginPage()),
    (_) => false,
  );
}
