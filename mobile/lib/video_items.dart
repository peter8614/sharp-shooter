import 'package:flutter/material.dart';
import 'package:chewie/chewie.dart';
import 'package:video_player/video_player.dart';

class VideoItems extends StatefulWidget {

  VideoItems({
    required this.videoPlayerController,
    required this.looping, required this.autoplay,
    Key? key,
  }) : super(key: key);
  final VideoPlayerController videoPlayerController;
  final bool looping;
  final bool autoplay;


  @override
  _VideoItemsState createState() => _VideoItemsState();
}

class _VideoItemsState extends State<VideoItems> {
  ChewieController? _chewieController;

  void _createChewieController() {
    _chewieController = ChewieController(
      videoPlayerController: widget.videoPlayerController,
      aspectRatio: widget.videoPlayerController.value.aspectRatio,
      autoInitialize: true,
      autoPlay: widget.autoplay,
      looping: widget.looping,
      errorBuilder: (context, errorMessage) => Center(
        child: Text(errorMessage, style: const TextStyle(color: Colors.white)),
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    _createChewieController();
  }

  @override
  void didUpdateWidget(covariant VideoItems oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.videoPlayerController != widget.videoPlayerController) {
      // Recreate Chewie when the user selects a different local recording.
      _chewieController?.dispose();
      _createChewieController();
    }
  }

  @override
  void dispose() {
    _chewieController?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(8.0),
      child: Chewie(
        controller: _chewieController!,
      ),
    );
  }
}
