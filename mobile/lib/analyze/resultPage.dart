import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:http/http.dart' as http;

import '../constants.dart';

class ResultPage extends StatefulWidget {
  ResultPage({
    Key? key,
    required this.videoFile,
    required this.duration
  }) : super(key: key);

  final XFile videoFile;
  final int duration;

  @override
  _ResultPageState createState() => _ResultPageState();
}

class _ResultPageState extends State<ResultPage> {
  String _uploadStatus = 'Uploading video securely...';

  @override
  void initState() {
    super.initState();
    sendVideoToServer(widget.videoFile.path);
  }

  Future<void> sendVideoToServer(String filePath) async {
    try {
      // The server derives the UID from this token instead of trusting form data.
      var request = http.MultipartRequest('POST', Uri.parse('$backend_Url/get_prediction'))
        ..headers.addAll(authenticatedHeaders())
        ..files.add(await http.MultipartFile.fromPath('video', filePath));

      // Send the request using the custom HTTP client
      var response = await customHttpClient.send(request);

      if (!mounted) return;
      if (response.statusCode == 202) {
        setState(() => _uploadStatus =
            'Upload complete. The analysis is queued and will appear in History.');
      } else {
        setState(() => _uploadStatus = 'The video could not be uploaded. Please try again.');
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _uploadStatus = 'The video could not be uploaded. Please check your connection.');
    }
  }

  String getEstimatedProcessingTime() {
    // Calculate estimated processing time per frame
    double processingTimePerFrame = 0.25; // 0.25 seconds per frame
    double fps = 30;
    double totalProcessingTime =
        (widget.duration * fps * processingTimePerFrame) / 60;
    return totalProcessingTime.toStringAsFixed(0) + ' minutes';
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
        automaticallyImplyLeading: false,
        elevation: 0,
        backgroundColor: primaryColor,
        toolbarHeight: 80,
        title: SizedBox(
          height: 80,
          width: double.infinity,
          child: Image.asset(
            'assets/logo.png',
            fit: BoxFit.fitHeight,
          ),
        ),
      ),
      body: Padding(
        padding: const EdgeInsets.symmetric(vertical: 30.0, horizontal: 12),
        child: Center(
          child: Card(
            color: secondaryColor,
            child: Padding(
              padding: const EdgeInsets.all(8.0),
              child: Column(
                children: [
                  Text(
                    _uploadStatus,
                    style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 10),
                  Text(
                    'Estimated processing time: ${getEstimatedProcessingTime()}',
                    style: const TextStyle(fontSize: 16),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(
                    height: 50,
                  ),
                  Container(
                    height: 200,
                    color: Colors.black,
                    child: Image.asset('assets/logo.png'),
                  ),
                  const SizedBox(
                    height: 20,
                  ),
                  const Text(
                    'The processed video and statistics will be available on the history page after processing.',
                    style: TextStyle(fontSize: 20),
                    textAlign: TextAlign.center,
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
