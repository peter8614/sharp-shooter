import 'package:shot_rater/analyze/analyzeVideoScreen.dart';
import 'package:shot_rater/history/historyScreen.dart';
import 'package:flutter/material.dart';

import 'constants.dart';

class RouteVolunteerPage extends StatefulWidget {
  const RouteVolunteerPage({Key? key}) : super(key: key);

  @override
  _RouteVolunteerPageState createState() => _RouteVolunteerPageState();
}

class _RouteVolunteerPageState extends State<RouteVolunteerPage> {
  int _selectedIndex = 0;
  static const TextStyle optionStyle =
      TextStyle(fontSize: 30, fontWeight: FontWeight.bold);
  static List<Widget>? _widgetOptions;

  @override
  void initState() {
    super.initState();
    _widgetOptions = [AnalyzeVideoPage(), HistoryPage(userId: user_id!,)];
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
        child: _widgetOptions!.elementAt(_selectedIndex),
      ),
      bottomNavigationBar: BottomNavigationBar(
        backgroundColor: primaryColor,
        type: BottomNavigationBarType.fixed,
        items: const <BottomNavigationBarItem>[
          BottomNavigationBarItem(
            icon: Icon(Icons.video_camera_front_outlined),
            label: 'Analyze',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.history),
            label: 'History',
          ),
        ],
        currentIndex: _selectedIndex,
        unselectedItemColor: const Color.fromRGBO(239, 226, 204, 1.0),
        selectedItemColor: secondaryColor,
        onTap: _onItemTapped,
      ),
    );
  }
}
