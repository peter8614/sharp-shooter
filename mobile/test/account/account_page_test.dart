import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shot_rater/account/account_page.dart';

void main() {
  testWidgets('account page exposes legal documents and deletion confirmation',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(home: AccountPage()));

    await tester.tap(find.text('Privacy Policy'));
    await tester.pumpAndSettle();
    expect(find.text('Information we collect'), findsOneWidget);

    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete account'));
    await tester.pumpAndSettle();
    expect(find.text('Delete account permanently?'), findsOneWidget);
    expect(find.text('Delete permanently'), findsOneWidget);

    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(find.text('Delete account permanently?'), findsNothing);
  });
}
