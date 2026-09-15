import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../api/api_client.dart';
import '../api/api_models.dart';
import '../constants.dart';
import '../routePage.dart';

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
        _jobId = null;
        _statusMessage = 'Uploading video securely...';
      });
    }

    try {
      final upload = await apiClient.uploadVideo(widget.videoFile.path);
      if (!mounted || _cancelPolling) return;
      setState(() {
        _jobId = upload.jobId;
        _statusMessage = 'Upload complete. Waiting for analysis to start...';
      });
      await _pollJob(upload.jobId);
    } on ApiException catch (error) {
      if (!mounted || error.isUnauthorized) return;
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

    while (mounted && !_cancelPolling) {
      final delayIndex =
          pollCount < delays.length ? pollCount : delays.length - 1;
      await Future<void>.delayed(delays[delayIndex]);
      if (!mounted || _cancelPolling) return;

      try {
        final job = await apiClient.getJob(jobId);
        consecutiveFailures = 0;
        if (!mounted || _cancelPolling) return;
        if (_applyJobStatus(job)) return;
      } on ApiException catch (error) {
        if (!mounted || error.isUnauthorized) return;
        consecutiveFailures++;
        if (consecutiveFailures >= 3 || error.statusCode == 404) {
          if (error.statusCode == 404) _jobId = null;
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
    if (jobId == null) {
      await _uploadAndTrack();
    } else {
      await _pollJob(jobId);
    }
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
                  if (_isWorking) ...[
                    const SizedBox(height: 10),
                    Text(
                      'Estimated processing time: ${getEstimatedProcessingTime()}',
                      style: const TextStyle(fontSize: 16),
                      textAlign: TextAlign.center,
                    ),
                  ],
                  const SizedBox(height: 24),
                  Container(
                    height: 200,
                    color: Colors.black,
                    child: Image.asset('assets/logo.png'),
                  ),
                  const SizedBox(height: 20),
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
                            builder: (_) =>
                                const RouteVolunteerPage(initialIndex: 1),
                          ),
                          (_) => false,
                        );
                      },
                      icon: const Icon(Icons.history),
                      label: const Text('View History'),
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
