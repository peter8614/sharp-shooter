import 'package:flutter/material.dart';

import '../constants.dart';

class ImageButton extends StatelessWidget {
  final String imagePath;
  final VoidCallback onPressed;
  final String label;

  const ImageButton({
    required this.imagePath,
    required this.onPressed,
    required this.label,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onPressed,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Container(
          height: 120,
          color: secondaryColor,
          child: Row(
            children: [
              Container(
                width: 100,
                height: 100,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.all(Radius.circular(20)),
                  color: primaryColor,
                  image: DecorationImage(
                    image: AssetImage(imagePath),
                    fit: BoxFit.fitHeight,
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.all(8.0),
                child: Text(
                  label,
                  style: TextStyle(fontSize: 20),
                ),
              )
            ],
          ),
        ),
      ),
    );
  }
}
