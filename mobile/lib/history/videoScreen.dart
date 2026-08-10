import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../constants.dart'; // Replace with your constants file for backend URL

class VideoPage extends StatefulWidget {
  const VideoPage({
    Key? key,
    required this.videoPath,
    required this.scores,
    required this.date,
  }) : super(key: key);

  final String videoPath;
  final List<Map<String, dynamic>> scores;
  final String date;

  @override
  State<VideoPage> createState() => _VideoPageState();
}

class _VideoPageState extends State<VideoPage> {
  VideoPlayerController? _controller;
  bool isLoading = true;

  @override
  void initState() {
    super.initState();
    _fetchVideoUrl();
  }

  Future<void> _fetchVideoUrl() async {
    const String apiUrl = "$backend_Url/get_video";
    try {
      final response = await customHttpClient.post(
        Uri.parse(apiUrl),
        headers: authenticatedHeaders(json: true),
        body: json.encode({
          "processed_video": widget.videoPath,
        }),
      );

      if (response.statusCode == 200) {
        final body = json.decode(response.body);
        final String videoUrl = body["video_url"];
        final controller = VideoPlayerController.networkUrl(Uri.parse(videoUrl));
        await controller.initialize();
        if (!mounted) {
          await controller.dispose();
          return;
        }
        setState(() {
          _controller = controller;
          isLoading = false;
        });
      } else {
        throw Exception('Failed to fetch video URL: ${response.body}');
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        isLoading = false;
      });
      print('Error fetching video URL: $e');
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios, color: Colors.white),
          onPressed: () => Navigator.of(context).pop(),
        ),
        elevation: 0,
        backgroundColor: Colors.blue,
        toolbarHeight: 100,
        title: Text(
          widget.date,
          style: const TextStyle(color: Colors.white, fontSize: 16),
        ),
      ),
      body: isLoading
          ? const Center(child: CircularProgressIndicator())
          : _controller != null && _controller!.value.isInitialized
          ? SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            const SizedBox(height: 20),
            AspectRatio(
              aspectRatio: _controller!.value.aspectRatio,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(10),
                child: VideoPlayer(_controller!),
              ),
            ),
            const SizedBox(height: 20),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                ElevatedButton.icon(
                  onPressed: () {
                    setState(() {
                      _controller!.seekTo(Duration.zero);
                      _controller!.play();
                    });
                  },
                  icon: const Icon(Icons.replay),
                  label: const Text('Replay'),
                ),
                const SizedBox(width: 10),
                ElevatedButton.icon(
                  onPressed: () {
                    setState(() {
                      _controller!.value.isPlaying
                          ? _controller!.pause()
                          : _controller!.play();
                    });
                  },
                  icon: Icon(_controller!.value.isPlaying
                      ? Icons.pause
                      : Icons.play_arrow),
                  label: Text(
                    _controller!.value.isPlaying ? 'Pause' : 'Play',
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),
          ],
        ),
      )
          : const Center(
        child: Text(
          'Failed to load video',
          style: TextStyle(fontSize: 18),
        ),
      ),
    );
  }
}
