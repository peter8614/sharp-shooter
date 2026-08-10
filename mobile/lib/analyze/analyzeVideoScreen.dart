import 'package:shot_rater/analyze/record/recordScreen.dart';
import 'package:shot_rater/analyze/uploadVideoPage.dart';
import 'package:flutter/material.dart';

import '../constants.dart';
import 'imageButton.dart';

class AnalyzeVideoPage extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        elevation: 0,
        backgroundColor: primaryColor,
        toolbarHeight: 120,
        title: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(
              height: 90,
              width: double.infinity,
              child: Image.asset(
                'assets/SharpShooter.png',
                fit: BoxFit.fitHeight,
              ),
            ),
          ],
        ),
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            ImageButton(
              imagePath: 'assets/upload.png',
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (context) => UploadPage()),
                );
              },
              label: 'Upload Video',
            ),
            SizedBox(height: 20),
            ImageButton(
              label: 'Record Video',
              imagePath: 'assets/record.png',
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (context) => CameraPage()),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

