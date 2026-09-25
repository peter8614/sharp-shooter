import 'dart:async';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../api/api_client.dart';
import '../api/app_jobs_client.dart';
import '../api/api_models.dart';
import '../constants.dart';
import '../routePage.dart';
import '../session_actions.dart';
import 'app_video_page.dart';
import 'coaching_presentation.dart';

class ResultPage extends StatefulWidget {
  const ResultPage({
    super.key,
    required this.videoFile,
    required this.duration,
  });

  final XFile videoFile;
  final int duration;

  @override
  State<ResultPage> createState() => _ResultPageState();
}

class _ResultPageState extends State<ResultPage> {
  String _statusMessage = 'Uploading video securely...';
  String? _jobId;
  bool _isWorking = true;
  bool _canRetry = false;
  bool _cancelPolling = false;
  AppUploadTicket? _appTicket;
  bool _appUploaded = false;
  Map<String, dynamic>? _appResult;
  bool _coachingPollTimedOut = false;
  bool _coachingPolling = false;

  @override
  void initState() {
    super.initState();
    _uploadAndTrack();
  }

  @override
  void dispose() {
    _cancelPolling = true;
    super.dispose();
  }

  Future<void> _uploadAndTrack() async {
    _cancelPolling = false;
    if (mounted) {
      setState(() {
        _isWorking = true;
        _canRetry = false;
        if (!useCognitoAppApi) _jobId = null;
        _statusMessage = 'Uploading video securely...';
      });
    }

    try {
      if (useCognitoAppApi) {
        final ticket =
            _appTicket ?? await appJobsClient.createJob(widget.videoFile.path);
        if (!mounted || _cancelPolling) return;
        _appTicket = ticket;
        _jobId = ticket.jobId;
        if (!_appUploaded) {
          await appJobsClient.uploadVideo(ticket, widget.videoFile.path);
          _appUploaded = true;
        }
        if (!mounted || _cancelPolling) return;
        setState(() => _statusMessage = 'Processing video...');
        await _pollJob(ticket.jobId);
        return;
      }
      final upload = await apiClient.uploadVideo(widget.videoFile.path);
      if (!mounted || _cancelPolling) return;
      setState(() {
        _jobId = upload.jobId;
        _statusMessage = 'Upload complete. Waiting for analysis to start...';
      });
      await _pollJob(upload.jobId);
    } on ApiException catch (error) {
      if (!mounted) return;
      if (error.isUnauthorized) {
        if (useCognitoAppApi) signOut(context);
        return;
      }
      if (useCognitoAppApi && error.statusCode == 403) {
        // A presigned URL can expire while the app is offline.
        _appTicket = null;
        _appUploaded = false;
        _jobId = null;
      }
      _showFailure(error.message);
    } catch (_) {
      if (!mounted) return;
      _showFailure(
          'The video could not be uploaded. Please check your connection.');
    }
  }

  Future<void> _pollJob(String jobId) async {
    const delays = <Duration>[
      Duration(seconds: 2),
      Duration(seconds: 3),
      Duration(seconds: 5),
      Duration(seconds: 8),
      Duration(seconds: 10),
    ];
    var pollCount = 0;
    var consecutiveFailures = 0;
    final deadline = DateTime.now().add(const Duration(minutes: 12));

    while (mounted && !_cancelPolling) {
      if (useCognitoAppApi && DateTime.now().isAfter(deadline)) {
        _showFailure(
            'Analysis is taking longer than expected. Retry status check.');
        return;
      }
      final delayIndex =
          pollCount < delays.length ? pollCount : delays.length - 1;
      await Future<void>.delayed(
          useCognitoAppApi ? const Duration(seconds: 3) : delays[delayIndex]);
      if (!mounted || _cancelPolling) return;

      try {
        if (useCognitoAppApi) {
          final job = await appJobsClient.getJob(jobId);
          consecutiveFailures = 0;
          if (!mounted || _cancelPolling) return;
          if (_applyAppJobStatus(job)) return;
          pollCount++;
          continue;
        }
        final job = await apiClient.getJob(jobId);
        consecutiveFailures = 0;
        if (!mounted || _cancelPolling) return;
        if (_applyJobStatus(job)) return;
      } on ApiException catch (error) {
        if (!mounted) return;
        if (error.isUnauthorized) {
          if (useCognitoAppApi) signOut(context);
          return;
        }
        consecutiveFailures++;
        if (consecutiveFailures >= 3 || error.statusCode == 404) {
          if (error.statusCode == 404) {
            _jobId = null;
            _appTicket = null;
            _appUploaded = false;
          }
          _showFailure(error.message);
          return;
        }
        setState(() {
          _statusMessage = 'Connection interrupted. Retrying job status...';
        });
      } catch (_) {
        consecutiveFailures++;
        if (consecutiveFailures >= 3) {
          _showFailure(
              'The analysis status could not be checked. Please retry.');
          return;
        }
      }
      pollCount++;
    }
  }

  bool _applyAppJobStatus(AppAnalysisJob job) {
    if (job.isComplete) {
      if (job.result == null) {
        _showFailure('The analysis result could not be read.');
        return true;
      }
      setState(() {
        _appResult = job.result;
        _coachingPollTimedOut = false;
        _isWorking = false;
        _canRetry = false;
        _statusMessage = 'Analysis complete';
      });
      if (_coachingIsPending(job.result)) {
        unawaited(_pollCoaching(job.jobId));
      }
      return true;
    }
    if (job.isFailed) {
      _jobId = null;
      _appTicket = null;
      _appUploaded = false;
      _showFailure(job.error ?? 'Video analysis failed.');
      return true;
    }
    setState(() => _statusMessage = job.status == 'processing'
        ? 'Processing video...'
        : 'Waiting to process video...');
    return false;
  }

  bool _applyJobStatus(AnalysisJob job) {
    if (job.isComplete) {
      setState(() {
        _isWorking = false;
        _canRetry = false;
        _statusMessage =
            'Analysis complete. The processed video and results are now available in History.';
      });
      return true;
    }
    if (job.isFailed) {
      _jobId = null;
      _showFailure(
          job.error ?? 'Video analysis failed. Please try another video.');
      return true;
    }

    setState(() {
      _statusMessage = job.status == 'processing'
          ? 'Analyzing shooting form and ball trajectory...'
          : 'Your analysis is queued...';
    });
    return false;
  }

  void _showFailure(String message) {
    if (!mounted) return;
    setState(() {
      _isWorking = false;
      _canRetry = true;
      _statusMessage = message;
    });
  }

  bool _coachingIsPending(Map<String, dynamic>? result) {
    final status = result?['coaching_status'];
    return status == 'queued' || status == 'processing';
  }

  Future<void> _pollCoaching(String jobId) async {
    if (_coachingPolling) return;
    _coachingPolling = true;
    final deadline = DateTime.now().add(const Duration(minutes: 2));
    try {
      while (mounted && !_cancelPolling && DateTime.now().isBefore(deadline)) {
        await Future<void>.delayed(const Duration(seconds: 5));
        if (!mounted || _cancelPolling) return;
        try {
          final job = await appJobsClient.getJob(jobId);
          if (!mounted || _cancelPolling) return;
          if (job.result != null) {
            setState(() => _appResult = job.result);
            if (!_coachingIsPending(job.result)) return;
          }
        } on ApiException catch (error) {
          if (error.isUnauthorized) {
            signOut(context);
            return;
          }
        } catch (_) {
          // Classification and evidence-based advice remain usable offline.
        }
      }
      if (mounted && !_cancelPolling) {
        setState(() => _coachingPollTimedOut = true);
      }
    } finally {
      _coachingPolling = false;
    }
  }

  Future<void> _retry() async {
    final jobId = _jobId;
    _cancelPolling = false;
    setState(() {
      _isWorking = true;
      _canRetry = false;
      _statusMessage = jobId == null
          ? 'Uploading video securely...'
          : 'Checking analysis status...';
    });
    if (jobId == null || (useCognitoAppApi && !_appUploaded)) {
      await _uploadAndTrack();
    } else {
      await _pollJob(jobId);
    }
  }

  Widget _appResultView() {
    final result = _appResult;
    if (result == null) return const SizedBox.shrink();
    final playerName = result['player_name'];
    final similarity = result['similarity_percentage'];
    final jobId = _jobId;
    final coachingStatus = result['coaching_status'];
    final coachingText = result['coaching_text'];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 16),
        Text(classificationText(
            'form', result['form_classification'], result['form_confidence'])),
        Text(classificationText(
            'trajectory',
            result['trajectory_classification'],
            result['trajectory_confidence'])),
        const Text(
            'Model confidence reflects the classification, not your chance of scoring or a guarantee of accuracy.'),
        if (jobId != null && result['processed_video_available'] == true)
          OutlinedButton.icon(
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(
              builder: (_) => AppVideoPage(
                jobId: jobId,
                videoKind: 'processed',
                title: 'Your analyzed shot',
              ),
            )),
            icon: const Icon(Icons.play_arrow),
            label: const Text('Play your analyzed video'),
          )
        else
          const Text('Analyzed video is not available for this job.'),
        const SizedBox(height: 12),
        if (playerName is String && playerName.isNotEmpty) ...[
          Text('Closest available reference: $playerName'),
          if (similarity is num)
            Text('Reference similarity: ${similarity.toStringAsFixed(1)}%'),
          const Text(
              'Experimental score among available reference clips, not all NBA players.'),
          if (jobId != null && result['reference_video_available'] == true)
            OutlinedButton.icon(
              onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => AppVideoPage(
                  jobId: jobId,
                  videoKind: 'reference',
                  title: '$playerName reference',
                ),
              )),
              icon: const Icon(Icons.sports_basketball),
              label: const Text('Play reference video'),
            )
          else
            const Text('Reference video is unavailable.'),
        ] else
          const Text('No NBA reference comparison is available for this job.'),
        const SizedBox(height: 16),
        const Text('Evidence-based guidance',
            style: TextStyle(fontWeight: FontWeight.bold)),
        ...evidenceBasedAdvice(result).map((advice) => Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(advice),
            )),
        if (coachingStatus == 'ready' &&
            coachingText is String &&
            coachingText.isNotEmpty) ...[
          const SizedBox(height: 16),
          const Text('AI coaching',
              style: TextStyle(fontWeight: FontWeight.bold)),
          Text(coachingText),
          const Text(
              'Generated from summarized pose measurements. Review it alongside your video.'),
        ] else if (_coachingIsPending(result)) ...[
          const SizedBox(height: 16),
          Text(_coachingPollTimedOut
              ? 'AI coaching is still processing. You can check again; your analysis above is ready.'
              : 'AI coaching is being generated separately. Your analysis above is ready.'),
          if (_coachingPollTimedOut && jobId != null)
            TextButton(
              onPressed: () {
                setState(() => _coachingPollTimedOut = false);
                unawaited(_pollCoaching(jobId));
              },
              child: const Text('Check AI coaching again'),
            ),
        ] else if (coachingStatus == 'unavailable') ...[
          const SizedBox(height: 16),
          const Text(
              'AI coaching is unavailable. Your analysis and evidence-based guidance remain available.'),
        ],
      ],
    );
  }

  String getEstimatedProcessingTime() {
    const processingTimePerFrame = 0.25;
    const fps = 30;
    final totalProcessingTime =
        (widget.duration * fps * processingTimePerFrame) / 60;
    return '${totalProcessingTime.toStringAsFixed(0)} minutes';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => Navigator.of(context).pop(),
          icon: const Icon(Icons.arrow_back_ios, color: Colors.white),
        ),
        automaticallyImplyLeading: false,
        elevation: 0,
        backgroundColor: primaryColor,
        toolbarHeight: 80,
        title: SizedBox(
          height: 80,
          width: double.infinity,
          child: Image.asset('assets/logo.png', fit: BoxFit.fitHeight),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(vertical: 30, horizontal: 12),
        child: Center(
          child: Card(
            color: secondaryColor,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (_isWorking) const CircularProgressIndicator(),
                  if (_isWorking) const SizedBox(height: 16),
                  Text(
                    _statusMessage,
                    style: const TextStyle(
                        fontSize: 20, fontWeight: FontWeight.bold),
                    textAlign: TextAlign.center,
                  ),
                  if (useCognitoAppApi) _appResultView(),
                  if (_isWorking) ...[
                    const SizedBox(height: 10),
                    Text(
                      'Estimated processing time: ${getEstimatedProcessingTime()}',
                      style: const TextStyle(fontSize: 16),
                      textAlign: TextAlign.center,
                    ),
                  ],
                  const SizedBox(height: 24),
                  if (!useCognitoAppApi) ...[
                    Container(
                      height: 200,
                      color: Colors.black,
                      child: Image.asset('assets/logo.png'),
                    ),
                    const SizedBox(height: 20),
                  ],
                  if (_canRetry)
                    ElevatedButton.icon(
                      onPressed: _retry,
                      icon: const Icon(Icons.refresh),
                      label: Text(_jobId == null
                          ? 'Retry upload'
                          : 'Retry status check'),
                    )
                  else if (!_isWorking)
                    ElevatedButton.icon(
                      onPressed: () {
                        Navigator.of(context).pushAndRemoveUntil(
                          MaterialPageRoute(
                            builder: (_) => RouteVolunteerPage(
                                initialIndex: useCognitoAppApi ? 0 : 1),
                          ),
                          (_) => false,
                        );
                      },
                      icon:
                          Icon(useCognitoAppApi ? Icons.check : Icons.history),
                      label: Text(useCognitoAppApi ? 'Done' : 'View History'),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
