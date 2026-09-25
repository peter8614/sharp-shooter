import 'package:flutter/material.dart';
import 'package:shot_rater/account/account_page.dart';
import 'package:shot_rater/analyze/analyzeVideoScreen.dart';
import 'package:shot_rater/history/historyScreen.dart';
import 'constants.dart';
import 'legal/legal_document_page.dart';
import 'session_actions.dart';

class RouteVolunteerPage extends StatefulWidget {
  const RouteVolunteerPage({
    super.key,
    this.initialIndex = 0,
  }) : assert(initialIndex >= 0 && initialIndex < 3);

  final int initialIndex;

  @override
  _RouteVolunteerPageState createState() => _RouteVolunteerPageState();
}

class _RouteVolunteerPageState extends State<RouteVolunteerPage> {
  late int _selectedIndex;
  late final List<Widget> _widgetOptions;

  @override
  void initState() {
    super.initState();
    _selectedIndex = widget.initialIndex;
    _widgetOptions = useCognitoAppApi
        ? [AnalyzeVideoPage(), const _AppAccountPage()]
        : [AnalyzeVideoPage(), const HistoryPage(), const AccountPage()];
  }

  void _onItemTapped(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: _widgetOptions.elementAt(_selectedIndex),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: _onItemTapped,
        destinations: [
          NavigationDestination(
            icon: Icon(Icons.video_camera_front_outlined),
            selectedIcon: Icon(Icons.video_camera_front),
            label: 'Analyze',
          ),
          if (!useCognitoAppApi)
            const NavigationDestination(
              icon: Icon(Icons.history_outlined),
              selectedIcon: Icon(Icons.history),
              label: 'History',
            ),
          const NavigationDestination(
            icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person),
            label: 'Account',
          ),
        ],
      ),
    );
  }
}

class _AppAccountPage extends StatelessWidget {
  const _AppAccountPage();

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Account')),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const ListTile(
              title: Text('Dev account'),
              subtitle: Text(
                  'Analysis history and account management are not yet available in the new API.'),
            ),
            ListTile(
              title: const Text('Privacy Policy'),
              onTap: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => const LegalDocumentPage(
                  document: LegalDocument.privacyPolicy,
                ),
              )),
            ),
            FilledButton(
              onPressed: () => signOut(context),
              child: const Text('Sign out'),
            ),
          ],
        ),
      );
}
