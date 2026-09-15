import 'package:flutter/material.dart';

import '../api/api_models.dart';
import 'videoScreen.dart';

class AnalysisDetailPage extends StatelessWidget {
  const AnalysisDetailPage({
    super.key,
    required this.item,
    required this.formattedDate,
  });

  final AnalysisHistoryItem item;
  final String formattedDate;

  Color _classificationColor(ShotClassification classification) {
    return switch (classification) {
      ShotClassification.good => Colors.green,
      ShotClassification.bad => Colors.orange,
      ShotClassification.unavailable => Colors.grey,
      ShotClassification.unknown => Colors.blueGrey,
    };
  }

  Widget _classificationTile(
    BuildContext context,
    String title,
    ShotClassification classification,
  ) {
    final color = _classificationColor(classification);
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: color.withValues(alpha: 0.15),
          child: Icon(Icons.sports_basketball, color: color),
        ),
        title: Text(title),
        trailing: Chip(
          label: Text(classification.displayName),
          side: BorderSide(color: color),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Analysis Details')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            formattedDate,
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 12),
          _classificationTile(
            context,
            'Shooting form',
            item.formClassification,
          ),
          _classificationTile(
            context,
            'Ball trajectory',
            item.trajectoryClassification,
          ),
          if (item.playerName != null || item.similarityPercentage != null) ...[
            const SizedBox(height: 16),
            Text('Reference comparison',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Card(
              child: ListTile(
                leading: const Icon(Icons.compare),
                title: Text(item.playerName ?? 'Reference player'),
                subtitle: item.similarityPercentage == null
                    ? null
                    : Text(
                        '${item.similarityPercentage!.toStringAsFixed(1)}% similarity'),
              ),
            ),
          ],
          if (item.llmAnalysis != null && item.llmAnalysis!.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text('Coaching feedback',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: SelectableText(item.llmAnalysis!),
              ),
            ),
          ],
          if (item.hasVideo) ...[
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => VideoPage(
                      date: formattedDate,
                      videoPath: item.processedVideo!,
                    ),
                  ),
                );
              },
              icon: const Icon(Icons.play_arrow),
              label: const Text('Play processed video'),
            ),
          ],
        ],
      ),
    );
  }
}
