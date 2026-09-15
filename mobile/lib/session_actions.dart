import 'package:flutter/material.dart';

import 'constants.dart';
import 'loginScreen.dart';

void signOut(BuildContext context) {
  sessionStore.clear();
  Navigator.of(context, rootNavigator: true).pushAndRemoveUntil(
    MaterialPageRoute(builder: (_) => const LoginPage()),
    (_) => false,
  );
}
