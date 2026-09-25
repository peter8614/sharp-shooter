import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../api/api_client.dart';
import '../constants.dart';
import '../session_actions.dart';

class AppVideoPage extends StatefulWidget {
  const AppVideoPage({
    super.key,
    required this.jobId,
    required this.videoKind,
    required this.title,
  });

  final String jobId;
  final String videoKind;
  final String title;

  @override
  State<AppVideoPage> createState() => _AppVideoPageState();
}

class _AppVideoPageState extends State<AppVideoPage> {
  VideoPlayerController? _controller;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    VideoPlayerController? next;
    try {
      // Fetch a fresh URL for every open/retry rather than storing an expired
      // bearer link in navigation or local storage.
      final url = await appJobsClient.getVideoUrl(widget.jobId, widget.videoKind);
      next = VideoPlayerController.networkUrl(url);
      await next.initialize();
      if (!mounted) {
        await next.dispose();
        return;
      }
      final previous = _controller;
      setState(() {
        _controller = next;
        _loading = false;
      });
      await previous?.dispose();
    } on ApiException catch (error) {
      await next?.dispose();
      if (!mounted) return;
      if (error.isUnauthorized) {
        signOut(context);
        return;
      }
      setState(() {
        _loading = false;
        _error = error.message;
      });
    } catch (_) {
      await next?.dispose();
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Video unavailable. Please retry.';
      });
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    return Scaffold(
      appBar: AppBar(title: Text(widget.title)),
      body: SafeArea(
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(_error!, textAlign: TextAlign.center),
                        const SizedBox(height: 12),
                        ElevatedButton(onPressed: _load, child: const Text('Retry')),
                      ],
                    ),
                  )
                : controller == null || !controller.value.isInitialized
                    ? const Center(child: Text('Video unavailable'))
                    : Column(
                        children: [
                          Expanded(
                            child: Center(
                              child: AspectRatio(
                                aspectRatio: controller.value.aspectRatio,
                                child: VideoPlayer(controller),
                              ),
                            ),
                          ),
                          IconButton(
                            onPressed: () {
                              controller.value.isPlaying
                                  ? controller.pause()
                                  : controller.play();
                              setState(() {});
                            },
                            icon: Icon(controller.value.isPlaying
                                ? Icons.pause
                                : Icons.play_arrow),
                          ),
                        ],
                      ),
      ),
    );
  }
}
