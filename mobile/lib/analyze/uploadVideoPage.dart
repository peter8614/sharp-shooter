import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../constants.dart';
import 'imageButton.dart';
import 'resultPage.dart';
import 'package:video_player/video_player.dart';
import 'package:flutter/cupertino.dart';
import '../video_items.dart';

class UploadPage extends StatefulWidget {
  UploadPage({
    Key? key,
  }) : super(key: key);

  @override
  _UploadPageState createState() => _UploadPageState();
}

class _UploadPageState extends State<UploadPage> {
  VideoPlayerController? _controller1;
  XFile? _video1File;

  final ImagePicker _picker = ImagePicker();

  Future<void> _setVideoController(XFile file, isVideo1) async {
    if (mounted) {
      VideoPlayerController controller;
      if (kIsWeb) {
        controller = VideoPlayerController.networkUrl(Uri.parse(file.path));
      } else {
        controller = VideoPlayerController.file(File(file.path));
      }
      await controller.initialize();
      if (!mounted) {
        await controller.dispose();
        return;
      }
      await _controller1?.dispose();
      setState(() {
        _controller1 = controller;
      });
    }
  }

  void _onVideo1ButtonPressed(ImageSource source) async {
    _video1File = await _picker.pickVideo(source: source);
    // The picker returns null when the user cancels; that is not an error.
    final selectedVideo = _video1File;
    if (selectedVideo != null) {
      await _setVideoController(selectedVideo, true);
    }
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
              const Expanded(
                  child: Text('Upload Video',
                      style: TextStyle(color: Colors.white)))
            ],
          ),
        ),
      ),
      body: _controller1 != null
          ? SingleChildScrollView(
              child: Padding(
                padding: const EdgeInsets.all(8.0),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const SizedBox(
                      height: 50,
                    ),
                    Container(
                        height: 100,
                        color: Colors.black,
                        child: Image.asset('assets/logo.png')),
                    const SizedBox(
                      height: 20,
                    ),
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
                            backgroundColor: primaryColor,
                          ),
                          onPressed: () {
                            Navigator.pushReplacement(
                                context,
                                CupertinoPageRoute(
                                    builder: (context) => ResultPage(
                                          duration: _controller1!
                                              .value.duration.inSeconds,
                                          videoFile: _video1File!,
                                        )));
                          },
                          child: const Text(
                            'Analyze Videos',
                            style: TextStyle(fontSize: 20, color: Colors.white),
                          )),
                    )
                  ],
                ),
              ),
            )
          : Center(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                  const SizedBox(
                    height: 50,
                  ),
                  Container(
                      height: 100,
                      color: Colors.black,
                      child: Image.asset('assets/logo.png')),
                  const SizedBox(
                    height: 20,
                  ),
                  Text(
                    appName,
                    style: const TextStyle(fontSize: 30),
                  ),
                  const SizedBox(
                    height: 50,
                  ),
                  ImageButton(
                    imagePath: 'assets/upload.png',
                    onPressed: () {
                      _onVideo1ButtonPressed(ImageSource.gallery);
                    },
                    label: 'Upload Video',
                  ),
                  const SizedBox(
                    height: 30,
                  ),
                ])),
    );
  }
}
