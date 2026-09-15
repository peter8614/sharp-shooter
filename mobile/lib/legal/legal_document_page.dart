import 'package:flutter/material.dart';

enum LegalDocument { privacyPolicy, termsOfService }

class LegalDocumentPage extends StatelessWidget {
  const LegalDocumentPage({
    super.key,
    required this.document,
  });

  final LegalDocument document;

  @override
  Widget build(BuildContext context) {
    final content = switch (document) {
      LegalDocument.privacyPolicy => _privacyPolicy,
      LegalDocument.termsOfService => _termsOfService,
    };
    return Scaffold(
      appBar: AppBar(title: Text(content.title)),
      body: SelectionArea(
        child: ListView.separated(
          padding: const EdgeInsets.all(20),
          itemCount: content.sections.length + 1,
          separatorBuilder: (_, __) => const SizedBox(height: 20),
          itemBuilder: (context, index) {
            if (index == 0) {
              return Text(
                'Last updated: September 15, 2026',
                style: Theme.of(context).textTheme.bodySmall,
              );
            }
            final section = content.sections[index - 1];
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  section.heading,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                ),
                const SizedBox(height: 8),
                Text(section.body),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _LegalContent {
  const _LegalContent(this.title, this.sections);

  final String title;
  final List<_LegalSection> sections;
}

class _LegalSection {
  const _LegalSection(this.heading, this.body);

  final String heading;
  final String body;
}

const _privacyPolicy = _LegalContent(
  'Privacy Policy',
  [
    _LegalSection(
      'Information we collect',
      'Sharp Shooter collects the email address and account identifier needed '
          'to authenticate you. When you choose to analyze a shot, we receive '
          'the video you record or select, including any audio in that video, '
          'and generate pose, trajectory, comparison, and coaching data.',
    ),
    _LegalSection(
      'How we use information',
      'We use this information to authenticate your account, process basketball '
          'shot videos, show your private analysis history, improve service '
          'reliability, and protect the service from abuse. We do not use your '
          'video or account data for advertising or cross-app tracking.',
    ),
    _LegalSection(
      'Service providers',
      'Firebase services provide authentication, database, and private file '
          'storage. When generated coaching is requested, anonymous aggregate '
          'pose measurements and controlled coaching labels may be sent to our '
          'AI service provider; raw videos and frame-by-frame landmarks are not '
          'sent for that coaching request.',
    ),
    _LegalSection(
      'Storage and retention',
      'Temporary server files are removed after video processing. Account-linked '
          'analysis records and private artifacts are retained so that you can '
          'view your history. They are deleted when you delete your account, '
          'except where retention is required by law or necessary to resolve '
          'security and service-integrity issues.',
    ),
    _LegalSection(
      'Your choices',
      'Camera, microphone, and photo-library access are requested only when '
          'needed for features you choose. You can deny those permissions in '
          'system settings, sign out at any time, or permanently delete your '
          'account and associated data from the Account page.',
    ),
    _LegalSection(
      'Contact',
      'For privacy questions or deletion assistance, use the support contact '
          'listed on the Sharp Shooter App Store product page.',
    ),
  ],
);

const _termsOfService = _LegalContent(
  'Terms of Service',
  [
    _LegalSection(
      'Using Sharp Shooter',
      'You may use Sharp Shooter to analyze basketball-shot videos that you '
          'have the right to record and upload. You are responsible for your '
          'account credentials and for activity performed through your account.',
    ),
    _LegalSection(
      'Acceptable use',
      'Do not upload unlawful, harmful, infringing, or unauthorized content; '
          'attempt to access another person\'s data; disrupt the service; or use '
          'automated means to overload or reverse engineer the service.',
    ),
    _LegalSection(
      'Analysis limitations',
      'Shot classifications, comparisons, and generated coaching are automated '
          'estimates for informational and training purposes. They are not '
          'medical advice, injury-prevention advice, or a substitute for a '
          'qualified coach or healthcare professional. Exercise within your '
          'abilities and stop if an activity causes pain.',
    ),
    _LegalSection(
      'Your content',
      'You retain ownership of videos you upload. You grant us permission to '
          'process and store them only as needed to provide and secure the '
          'service. Your analysis history is private to your authenticated account.',
    ),
    _LegalSection(
      'Availability and changes',
      'We may maintain, improve, or change the service and cannot guarantee that '
          'every analysis will complete or that the service will always be '
          'available. Material changes to these terms will be communicated '
          'through the app or its official product page.',
    ),
    _LegalSection(
      'Ending your account',
      'You may stop using the service at any time. The Account page lets you '
          'permanently delete your account and associated private analysis data.',
    ),
  ],
);
