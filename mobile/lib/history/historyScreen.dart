import 'dart:convert';
import 'package:shot_rater/history/videoScreen.dart';
import 'package:flutter/material.dart';

import '../constants.dart';

class HistoryPage extends StatefulWidget {
  const HistoryPage({Key? key, required this.userId}) : super(key: key);

  final String userId;

  @override
  State<HistoryPage> createState() => _HistoryPageState();
}

class _HistoryPageState extends State<HistoryPage> {
  bool _isAscending = true;
  List<Map<String, dynamic>> userHistory = [];
  bool isLoading = true;

  @override
  void initState() {
    super.initState();
    fetchUserHistory();
  }

  Future<void> fetchUserHistory() async {
    const String apiUrl = "$backend_Url/get_user_history";
    try {
      final response = await customHttpClient.post(
        Uri.parse(apiUrl),
        headers: authenticatedHeaders(json: true),
        body: json.encode({}),
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        if (!mounted) return;
        setState(() {
          userHistory = List<Map<String, dynamic>>.from(data['history']);
          isLoading = false;
        });
      } else {
        if (!mounted) return;
        setState(() {
          isLoading = false;
        });
        print('Error fetching user history: ${response.body}');
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        isLoading = false;
      });
      print('Error: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        elevation: 0,
        backgroundColor: primaryColor,
        toolbarHeight: 120,
        title: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(
              height: 90,
              width: double.infinity,
              child: Image.asset(
                'assets/SharpShooter.png',
                fit: BoxFit.fitHeight,
              ),
            ),
          ],
        ),
      ),
      body: isLoading
          ? const Center(child: CircularProgressIndicator())
          : Column(
        children: [
          Card(
            color: Colors.grey[300],
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 8.0),
                  child: Text('Sort by Date/Time:'),
                ),
                IconButton(
                  onPressed: () {
                    setState(() {
                      _isAscending = !_isAscending;
                      userHistory.sort((a, b) {
                        final aTimestamp =
                        DateTime.parse(a['timestamp']);
                        final bTimestamp =
                        DateTime.parse(b['timestamp']);
                        return _isAscending
                            ? aTimestamp.compareTo(bTimestamp)
                            : bTimestamp.compareTo(aTimestamp);
                      });
                    });
                  },
                  icon: Icon(_isAscending
                      ? Icons.arrow_drop_up
                      : Icons.arrow_drop_down_sharp),
                ),
              ],
            ),
          ),
          Expanded(
            child: userHistory.isEmpty
                ? const Center(child: Text('No history found'))
                : Padding(
              padding: const EdgeInsets.all(8.0),
              child: ListView.builder(
                itemCount: userHistory.length,
                itemBuilder: (context, index) {
                  final historyItem = userHistory[index];
                  final timestamp =
                  historyItem['timestamp'];
                  final form_classification = historyItem["form_classification"];
                  final trajectory_classification = historyItem["trajectory_classification"];
                  final avi_file_path = historyItem["processed_video"];

                  return Card(
                    color: secondaryColor,
                    child: ListTile(
                      title: Text(
                          'Date/Time: ${timestamp.toString().substring(0, 16)}'),
                      subtitle: Text(
                          'Form: $form_classification\nTrajectory: $trajectory_classification'),
                      trailing: IconButton(
                        icon: const Icon(Icons.play_arrow,
                            color: Colors.white),
                        style: ElevatedButton.styleFrom(
                            backgroundColor: primaryColor),
                        onPressed: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (context) => VideoPage(
                                date: timestamp
                                    .toString()
                                    .substring(0, 16),
                                videoPath: avi_file_path,
                                scores: [], // Add relevant data if needed
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  );
                },
              ),
            ),
          ),
        ],
      ),
    );
  }
}
