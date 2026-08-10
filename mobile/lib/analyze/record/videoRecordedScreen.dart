import 'dart:io';

import 'package:shot_rater/video_items.dart';
import 'package:camera/camera.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../../constants.dart';
import '../resultPage.dart';

class RecordedVideoPage extends StatefulWidget {
  final String filePath;

  const RecordedVideoPage({Key? key, required this.filePath}) : super(key: key);

  @override
  _RecordedVideoPageState createState() => _RecordedVideoPageState();
}

class _RecordedVideoPageState extends State<RecordedVideoPage> {
  VideoPlayerController? _controller1;

  @override
  void initState() {
    super.initState();
    _setVideoController();
  }

  Future<void> _setVideoController() async {
    // Camera recordings are local files, not network URLs.
    final controller = VideoPlayerController.file(File(widget.filePath));
    await controller.initialize();
    if (!mounted) {
      await controller.dispose();
      return;
    }
    setState(() => _controller1 = controller);
  }

  @override
  void dispose() {
    _controller1?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: GestureDetector(
          onTap: () {
            Navigator.of(context).pop();
          },
          child: const Icon(
            Icons.arrow_back_ios,
            color: Colors.white,
          ),
        ),
        elevation: 0,
        backgroundColor: primaryColor,
        toolbarHeight: 100,
        title: SizedBox(
          height: 80,
          width: double.infinity,
          child: Column(
            children: [
              Expanded(
                flex: 2,
                child: Image.asset(
                  'assets/logo.png',
                  fit: BoxFit.fitHeight,
                ),
              ),
              const Expanded(child: Text('Upload Video'))
            ],
          ),
        ),
      ),
      body: _controller1 != null
          ? SingleChildScrollView(
              child: Padding(
                padding: const EdgeInsets.only(
                    top: 30.0, left: 8, right: 8, bottom: 12),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Container(
                      color: Colors.black,
                      height: 250,
                      child: VideoItems(
                        videoPlayerController: _controller1!,
                        autoplay: false,
                        looping: false,
                      ),
                    ),
                    const SizedBox(
                      height: 20,
                    ),
                    SizedBox(
                      width: 250,
                      height: 50,
                      child: ElevatedButton(
                          style: ElevatedButton.styleFrom(
                            backgroundColor:
                                primaryColor,
                          ),
                          onPressed: () {
                            Navigator.pushReplacement(
                                context,
                                CupertinoPageRoute(
                                    builder: (context) => ResultPage(
                                          videoFile: XFile(widget.filePath),
                                          duration: _controller1!
                                              .value.duration.inSeconds,
                                        )));
                          },
                          child: const Text(
                            'Analyze Videos',
                            style:
                                TextStyle(fontSize: 20, color: Colors.black54),
                          )),
                    )
                  ],
                ),
              ),
            )
          : const Center(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                  Text(
                    'Loading Video Error',
                    style: TextStyle(fontSize: 30),
                  ),
                ])),
    );
  }
}
