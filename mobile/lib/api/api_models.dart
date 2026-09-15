class AuthSession {
  const AuthSession({
    required this.userId,
    required this.idToken,
    this.refreshToken,
    this.expiresAt,
  });

  final String userId;
  final String idToken;
  final String? refreshToken;
  final DateTime? expiresAt;

  bool get canRefresh => refreshToken != null && refreshToken!.isNotEmpty;
  bool get shouldRefresh =>
      expiresAt != null &&
      !DateTime.now()
          .toUtc()
          .add(const Duration(minutes: 1))
          .isBefore(expiresAt!);

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    final userId = json['user_id'];
    final idToken = json['idToken'];
    final rawRefreshToken = json['refreshToken'];
    final rawExpiresIn = json['expiresIn'];
    if (userId is! String ||
        userId.isEmpty ||
        idToken is! String ||
        idToken.isEmpty) {
      throw const FormatException('The authentication response is incomplete.');
    }
    final expiresInSeconds = rawExpiresIn is num
        ? rawExpiresIn.toInt()
        : int.tryParse(rawExpiresIn?.toString() ?? '');
    return AuthSession(
      userId: userId,
      idToken: idToken,
      refreshToken: rawRefreshToken is String && rawRefreshToken.isNotEmpty
          ? rawRefreshToken
          : null,
      expiresAt: expiresInSeconds == null
          ? null
          : DateTime.now().toUtc().add(Duration(seconds: expiresInSeconds)),
    );
  }
}

class UploadJob {
  const UploadJob({required this.jobId, required this.status});

  final String jobId;
  final String status;

  factory UploadJob.fromJson(Map<String, dynamic> json) {
    final jobId = json['job_id'];
    final status = json['status'];
    if (jobId is! String ||
        jobId.isEmpty ||
        status is! String ||
        status.isEmpty) {
      throw const FormatException('The upload response is incomplete.');
    }
    return UploadJob(jobId: jobId, status: status);
  }
}

class AnalysisJob {
  const AnalysisJob({
    required this.status,
    this.analysisId,
    this.error,
  });

  final String status;
  final String? analysisId;
  final String? error;

  bool get isComplete => status == 'complete';
  bool get isFailed => status == 'failed';
  bool get isTerminal => isComplete || isFailed;

  factory AnalysisJob.fromJson(Map<String, dynamic> json) {
    final status = json['status'];
    if (status is! String || status.isEmpty) {
      throw const FormatException('The job response is incomplete.');
    }
    return AnalysisJob(
      status: status,
      analysisId:
          json['analysis_id'] is String ? json['analysis_id'] as String : null,
      error: json['error'] is String ? json['error'] as String : null,
    );
  }
}

enum ShotClassification {
  good,
  bad,
  unavailable,
  unknown;

  factory ShotClassification.fromJson(Object? value) {
    return switch (value) {
      'good' => ShotClassification.good,
      'bad' => ShotClassification.bad,
      'unavailable' => ShotClassification.unavailable,
      _ => ShotClassification.unknown,
    };
  }

  String get displayName => switch (this) {
        ShotClassification.good => 'Good',
        ShotClassification.bad => 'Needs improvement',
        ShotClassification.unavailable => 'Unavailable',
        ShotClassification.unknown => 'Unknown',
      };
}

class AnalysisHistoryItem {
  const AnalysisHistoryItem({
    required this.analysisId,
    required this.formClassification,
    required this.trajectoryClassification,
    required this.processedVideo,
    required this.timestamp,
    this.llmAnalysis,
    this.playerRecording,
    this.playerName,
    this.similarityPercentage,
  });

  final String? analysisId;
  final ShotClassification formClassification;
  final ShotClassification trajectoryClassification;
  final String? processedVideo;
  final DateTime? timestamp;
  final String? llmAnalysis;
  final String? playerRecording;
  final String? playerName;
  final double? similarityPercentage;

  bool get hasVideo => processedVideo != null && processedVideo!.isNotEmpty;

  factory AnalysisHistoryItem.fromJson(Map<String, dynamic> json) {
    final rawTimestamp = json['timestamp'];
    return AnalysisHistoryItem(
      analysisId:
          json['analysis_id'] is String ? json['analysis_id'] as String : null,
      formClassification:
          ShotClassification.fromJson(json['form_classification']),
      trajectoryClassification:
          ShotClassification.fromJson(json['trajectory_classification']),
      processedVideo: json['processed_video'] is String
          ? json['processed_video'] as String
          : null,
      timestamp:
          rawTimestamp is String ? DateTime.tryParse(rawTimestamp) : null,
      llmAnalysis: json['llm_analysis'] is String
          ? json['llm_analysis'] as String
          : null,
      playerRecording: json['player_recording'] is String
          ? json['player_recording'] as String
          : null,
      playerName:
          json['player_name'] is String ? json['player_name'] as String : null,
      similarityPercentage: json['similarity_percentage'] is num
          ? (json['similarity_percentage'] as num).toDouble()
          : null,
    );
  }
}
