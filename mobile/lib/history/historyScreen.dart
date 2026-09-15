import 'package:flutter/material.dart';
import 'package:shot_rater/history/videoScreen.dart';

import '../api/api_client.dart';
import '../api/api_models.dart';
import '../constants.dart';
import '../session_actions.dart';
import 'analysis_detail_page.dart';

class HistoryPage extends StatefulWidget {
  const HistoryPage({super.key});

  @override
  State<HistoryPage> createState() => _HistoryPageState();
}

class _HistoryPageState extends State<HistoryPage> {
  bool _isAscending = false;
  List<AnalysisHistoryItem> _userHistory = const [];
  bool _isLoading = true;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _fetchUserHistory();
  }

  Future<void> _fetchUserHistory({bool showLoading = true}) async {
    if (showLoading && mounted) {
      setState(() {
        _isLoading = true;
        _errorMessage = null;
      });
    }

    try {
      final history = await apiClient.getHistory();
      _sortHistory(history);
      if (!mounted) return;
      setState(() {
        _userHistory = history;
        _isLoading = false;
        _errorMessage = null;
      });
    } on ApiException catch (error) {
      if (!mounted || error.isUnauthorized) return;
      setState(() {
        _isLoading = false;
        _errorMessage = error.message;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _errorMessage = 'History could not be loaded. Please try again.';
      });
    }
  }

  void _sortHistory(List<AnalysisHistoryItem> history) {
    history.sort((a, b) {
      final aTimestamp = a.timestamp;
      final bTimestamp = b.timestamp;
      if (aTimestamp == null && bTimestamp == null) return 0;
      if (aTimestamp == null) return 1;
      if (bTimestamp == null) return -1;
      return _isAscending
          ? aTimestamp.compareTo(bTimestamp)
          : bTimestamp.compareTo(aTimestamp);
    });
  }

  void _toggleSort() {
    setState(() {
      _isAscending = !_isAscending;
      _sortHistory(_userHistory);
    });
  }

  String _formatTimestamp(DateTime? value) {
    if (value == null) return 'Date unavailable';
    final local = value.toLocal();
    String twoDigits(int number) => number.toString().padLeft(2, '0');
    return '${local.year}-${twoDigits(local.month)}-${twoDigits(local.day)} '
        '${twoDigits(local.hour)}:${twoDigits(local.minute)}';
  }

  Color _classificationColor(ShotClassification classification) {
    return switch (classification) {
      ShotClassification.good => Colors.green.shade700,
      ShotClassification.bad => Colors.orange.shade800,
      ShotClassification.unavailable => Colors.grey.shade700,
      ShotClassification.unknown => Colors.blueGrey.shade700,
    };
  }

  Widget _classificationLabel(
    String prefix,
    ShotClassification classification,
  ) {
    final color = _classificationColor(classification);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        '$prefix: ${classification.displayName}',
        style: TextStyle(color: color, fontWeight: FontWeight.w600),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        elevation: 0,
        backgroundColor: primaryColor,
        toolbarHeight: 120,
        title: SizedBox(
          height: 90,
          width: double.infinity,
          child: Image.asset('assets/SharpShooter.png', fit: BoxFit.fitHeight),
        ),
        actions: [
          IconButton(
            onPressed: () => signOut(context),
            tooltip: 'Sign out',
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_errorMessage != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_errorMessage!, textAlign: TextAlign.center),
              const SizedBox(height: 16),
              ElevatedButton.icon(
                onPressed: _fetchUserHistory,
                icon: const Icon(Icons.refresh),
                label: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }

    return Column(
      children: [
        Card(
          color: Colors.grey[300],
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 8),
                child: Text('Sort by Date/Time:'),
              ),
              IconButton(
                onPressed: _toggleSort,
                tooltip: _isAscending ? 'Oldest first' : 'Newest first',
                icon: Icon(
                  _isAscending
                      ? Icons.arrow_drop_up
                      : Icons.arrow_drop_down_sharp,
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: () => _fetchUserHistory(showLoading: false),
            child: _userHistory.isEmpty
                ? ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    children: const [
                      SizedBox(height: 180),
                      Center(child: Text('No history found')),
                    ],
                  )
                : ListView.builder(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.all(8),
                    itemCount: _userHistory.length,
                    itemBuilder: (context, index) {
                      final item = _userHistory[index];
                      final processedVideo = item.processedVideo;
                      final formattedDate = _formatTimestamp(item.timestamp);
                      return Card(
                        child: ListTile(
                          contentPadding: const EdgeInsets.symmetric(
                            horizontal: 16,
                            vertical: 8,
                          ),
                          title: Text(
                            formattedDate,
                            style: const TextStyle(fontWeight: FontWeight.w600),
                          ),
                          subtitle: Padding(
                            padding: const EdgeInsets.only(top: 8),
                            child: Wrap(
                              spacing: 8,
                              runSpacing: 6,
                              children: [
                                _classificationLabel(
                                  'Form',
                                  item.formClassification,
                                ),
                                _classificationLabel(
                                  'Trajectory',
                                  item.trajectoryClassification,
                                ),
                              ],
                            ),
                          ),
                          trailing: IconButton(
                            icon: const Icon(Icons.play_arrow),
                            tooltip: !item.hasVideo
                                ? 'Video unavailable'
                                : 'Play video',
                            onPressed: !item.hasVideo
                                ? null
                                : () {
                                    Navigator.push(
                                      context,
                                      MaterialPageRoute(
                                        builder: (_) => VideoPage(
                                          date: formattedDate,
                                          videoPath: processedVideo!,
                                        ),
                                      ),
                                    );
                                  },
                          ),
                          onTap: () {
                            Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder: (_) => AnalysisDetailPage(
                                  item: item,
                                  formattedDate: formattedDate,
                                ),
                              ),
                            );
                          },
                        ),
                      );
                    },
                  ),
          ),
        ),
      ],
    );
  }
}
