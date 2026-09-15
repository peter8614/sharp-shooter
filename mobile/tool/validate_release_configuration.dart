import 'dart:io';

import 'package:shot_rater/config/release_configuration.dart';

void main(List<String> arguments) {
  if (arguments.length != 1) {
    stderr.writeln(
      'Usage: dart run tool/validate_release_configuration.dart <BACKEND_URL>',
    );
    exitCode = 64;
    return;
  }

  final error = productionBackendUrlError(arguments.single);
  if (error != null) {
    stderr.writeln('Release configuration error: $error');
    exitCode = 64;
    return;
  }
  stdout.writeln('Release backend configuration is valid.');
}
