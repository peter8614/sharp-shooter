import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shot_rater/main.dart';
import 'package:shot_rater/constants.dart';

void main() {
  testWidgets('splash screen opens the login form', (tester) async {
    FlutterSecureStorage.setMockInitialValues({});
    await tester.pumpWidget(const MyApp());
    expect(find.text('Version'), findsOneWidget);

    // Advance the intentional splash delay and finish the navigation animation.
    await tester.pump();
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(find.text(useCognitoAppApi ? 'Sign in securely' : 'Login'),
        findsOneWidget);
  });
}
