import 'package:flutter_test/flutter_test.dart';
import 'package:shot_rater/analyze/coaching_presentation.dart';

void main() {
  test('classification displays confidence without internal labels', () {
    expect(classificationText('trajectory', 'bad', 0.875),
        'Ball trajectory: Bad — needs attention (model confidence 88%)');
    expect(classificationText('form', 'good', 0.921),
        'Shooting form: Good — no clear issue detected (model confidence 92%)');
    expect(classificationText('form', 'unavailable', null),
        'Shooting form: Unavailable — not enough evidence');
  });

  test('generic trajectory result does not invent a mechanical cause', () {
    final advice = evidenceBasedAdvice({
      'form_classification': 'good',
      'trajectory_classification': 'bad',
      'coaching_labels': [
        {'code': 'trajectory_model_flagged', 'status': 'needs_attention'}
      ],
    });
    expect(advice.single, contains('cannot identify the cause'));
    expect(advice.single, isNot(contains('needs_attention')));
  });

  test('specific evidence is bounded to known codes and at most two', () {
    final advice = evidenceBasedAdvice({
      'form_classification': 'bad',
      'coaching_labels': [
        for (final code in [
          'left_elbow_angle_below_good_reference',
          'right_wrist_lower_than_good_reference',
          'unknown_internal_label',
        ])
          {
            'code': code,
            'evidence': {
              'observed': 1,
              'reference_low': 2,
              'reference_high': 3
            },
          }
      ],
    });
    expect(advice, hasLength(2));
    expect(advice.join(' '), contains('training reference band'));
    expect(advice.join(' '), isNot(contains('unknown_internal_label')));
  });
}
