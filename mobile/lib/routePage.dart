import 'package:flutter/material.dart';
import 'package:shot_rater/account/account_page.dart';
import 'package:shot_rater/analyze/analyzeVideoScreen.dart';
import 'package:shot_rater/history/historyScreen.dart';

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
    _widgetOptions = [
      AnalyzeVideoPage(),
      const HistoryPage(),
      const AccountPage(),
    ];
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
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.video_camera_front_outlined),
            selectedIcon: Icon(Icons.video_camera_front),
            label: 'Analyze',
          ),
          NavigationDestination(
            icon: Icon(Icons.history_outlined),
            selectedIcon: Icon(Icons.history),
            label: 'History',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person),
            label: 'Account',
          ),
        ],
      ),
    );
  }
}
