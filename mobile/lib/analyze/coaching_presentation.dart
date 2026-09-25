// User-facing, evidence-bounded wording for the asynchronous App result.
// The model's internal codes and statuses must never be rendered verbatim.

String classificationText(
    String domain, Object? classification, Object? confidence) {
  final label = classification == 'good'
      ? 'Good — no clear issue detected'
      : classification == 'bad'
          ? 'Bad — needs attention'
          : 'Unavailable — not enough evidence';
  final subject = domain == 'form' ? 'Shooting form' : 'Ball trajectory';
  final value = confidence is num && confidence >= 0 && confidence <= 1
      ? ' (model confidence ${(confidence * 100).toStringAsFixed(0)}%)'
      : '';
  return '$subject: $label$value';
}

const _specificFindings = <String, String>{
  'left_elbow_angle_below_good_reference':
      'Your average left-elbow angle falls below the training reference band',
  'left_elbow_angle_above_good_reference':
      'Your average left-elbow angle falls above the training reference band',
  'right_elbow_angle_below_good_reference':
      'Your average right-elbow angle falls below the training reference band',
  'right_elbow_angle_above_good_reference':
      'Your average right-elbow angle falls above the training reference band',
  'left_wrist_higher_than_good_reference':
      'Your left-wrist position falls above the training reference band',
  'left_wrist_lower_than_good_reference':
      'Your left-wrist position falls below the training reference band',
  'right_wrist_higher_than_good_reference':
      'Your right-wrist position falls above the training reference band',
  'right_wrist_lower_than_good_reference':
      'Your right-wrist position falls below the training reference band',
};

List<String> evidenceBasedAdvice(Map<String, dynamic> result) {
  final labels = result['coaching_labels'];
  final findings = <String>[];
  if (labels is List) {
    for (final item in labels) {
      if (item is! Map) {
        continue;
      }
      final code = item['code'];
      final evidence = item['evidence'];
      if (code is! String ||
          evidence is! Map ||
          evidence['observed'] is! num ||
          evidence['reference_low'] is! num ||
          evidence['reference_high'] is! num) {
        continue;
      }
      final description = _specificFindings[code];
      if (description != null) {
        findings.add(
            '$description. Try comfortable close-range shots and compare recordings from the same camera position. This training reference is not a universal ideal.');
      }
      if (findings.length == 2) {
        break;
      }
    }
  }
  if (findings.isNotEmpty) {
    return findings;
  }
  if (result['form_classification'] == 'bad') {
    findings.add(
        'The form model flagged a concern, but the available evidence does not identify a specific cause. Record the full shot from the same camera position and retest.');
  }
  if (result['trajectory_classification'] == 'bad') {
    findings.add(
        'The trajectory model flagged a concern, but it cannot identify the cause. Record several close-range shots from the same camera position and compare results.');
  }
  if (findings.isEmpty) {
    findings.add(
        'The models did not identify a specific issue. This does not prove ideal form; retest using the same recording setup.');
  }
  return findings;
}
