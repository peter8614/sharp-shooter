import 'package:flutter/material.dart';
import 'package:flutter_appauth/flutter_appauth.dart';

import 'api/api_client.dart';
import 'constants.dart';
import 'legal/legal_document_page.dart';
import 'routePage.dart';
import 'signupScreen.dart';

class LoginPage extends StatelessWidget {
  const LoginPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        elevation: 0,
        automaticallyImplyLeading: false,
        backgroundColor: primaryColor,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.only(
            bottomLeft: Radius.circular(50.0),
            bottomRight: Radius.circular(50.0),
          ),
        ),
        toolbarHeight: 150,
        flexibleSpace: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Center(
              child: Container(
                height: 120,
                width: 110,
                decoration: const BoxDecoration(
                  image: DecorationImage(
                      image: AssetImage('assets/SharpShooter.png'),
                      fit: BoxFit.fitHeight),
                ),
              ),
            )
          ],
        ),
      ),
      body: useCognitoAppApi
          ? const _CognitoLogin()
          : ListView(
              padding: const EdgeInsets.all(8.0),
              children: <Widget>[
                const SizedBox(height: 50),
                Text(appName,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                        fontWeight: FontWeight.bold, fontSize: 30)),
                Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: LoginForm(),
                ),
                const SizedBox(height: 20),
                Row(
                  children: <Widget>[
                    const SizedBox(width: 30),
                    const Text('New here ? ',
                        style: TextStyle(
                            fontWeight: FontWeight.bold, fontSize: 20)),
                    GestureDetector(
                      onTap: () {
                        Navigator.push(context,
                            MaterialPageRoute(builder: (context) => Signup()));
                      },
                      child: const Text('Get Registered Now!!',
                          style: TextStyle(fontSize: 20, color: Colors.blue)),
                    )
                  ],
                ),
                const SizedBox(height: 16),
                Center(
                  child: Wrap(
                    alignment: WrapAlignment.center,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      TextButton(
                        onPressed: () => Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => const LegalDocumentPage(
                              document: LegalDocument.privacyPolicy,
                            ),
                          ),
                        ),
                        child: const Text('Privacy Policy'),
                      ),
                      const Text('•'),
                      TextButton(
                        onPressed: () => Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => const LegalDocumentPage(
                              document: LegalDocument.termsOfService,
                            ),
                          ),
                        ),
                        child: const Text('Terms of Service'),
                      ),
                    ],
                  ),
                ),
              ],
            ),
    );
  }
}

class _CognitoLogin extends StatefulWidget {
  const _CognitoLogin();

  @override
  State<_CognitoLogin> createState() => _CognitoLoginState();
}

class _CognitoLoginState extends State<_CognitoLogin> {
  bool _busy = false;

  Future<void> _signIn() async {
    setState(() => _busy = true);
    try {
      await cognitoAuth.signIn();
      if (!mounted) return;
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const RouteVolunteerPage()),
        (_) => false,
      );
    } on FlutterAppAuthUserCancelledException {
      // Closing the browser is not a sign-in error.
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Sign in failed. Please try again.'),
      ));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Sign in to analyze your shot.'),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _busy ? null : _signIn,
                child: _busy
                    ? const CircularProgressIndicator()
                    : const Text('Sign in securely'),
              ),
              const SizedBox(height: 12),
              const Text('Dev access is currently invitation-only.'),
              TextButton(
                onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => const LegalDocumentPage(
                    document: LegalDocument.privacyPolicy,
                  ),
                )),
                child: const Text('Privacy Policy'),
              ),
            ],
          ),
        ),
      );
}

class LoginForm extends StatefulWidget {
  LoginForm({Key? key}) : super(key: key);

  @override
  _LoginFormState createState() => _LoginFormState();
}

class _LoginFormState extends State<LoginForm> {
  final _formKey = GlobalKey<FormState>();

  String? email;
  String? password;

  bool _obscureText = true;
  bool _isSubmitting = false;

  // Helper method for user login
  Future<void> loginUser(String email, String password) async {
    setState(() => _isSubmitting = true);
    try {
      await apiClient.signIn(email, password);
      if (!mounted) return;
      Navigator.pushAndRemoveUntil(
        context,
        MaterialPageRoute(builder: (_) => const RouteVolunteerPage()),
        (_) => false,
      );
    } on ApiException catch (error) {
      _showError(error.message);
    } catch (_) {
      _showError('Sign in failed. Please try again.');
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  void _showError(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message, style: const TextStyle(fontSize: 16))),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Form(
      key: _formKey,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: <Widget>[
          // Email
          TextFormField(
            decoration: const InputDecoration(
              prefixIcon: Icon(Icons.email_outlined),
              labelText: 'Email',
              border: OutlineInputBorder(
                borderRadius: BorderRadius.all(
                  Radius.circular(100.0),
                ),
              ),
            ),
            validator: (value) {
              if (value!.isEmpty) {
                return 'Please enter your email.';
              }
              return null;
            },
            onSaved: (val) {
              email = val;
            },
          ),
          const SizedBox(height: 20),

          // Password
          TextFormField(
            decoration: InputDecoration(
              labelText: 'Password',
              prefixIcon: const Icon(Icons.lock_outline),
              border: const OutlineInputBorder(
                borderRadius: BorderRadius.all(
                  Radius.circular(100.0),
                ),
              ),
              suffixIcon: GestureDetector(
                onTap: () {
                  setState(() {
                    _obscureText = !_obscureText;
                  });
                },
                child: Icon(
                  _obscureText ? Icons.visibility_off : Icons.visibility,
                ),
              ),
            ),
            obscureText: _obscureText,
            onSaved: (val) {
              password = val;
            },
            validator: (value) {
              if (value!.isEmpty) {
                return 'Please enter your password.';
              }
              return null;
            },
          ),
          const SizedBox(height: 30),

          // Login Button
          SizedBox(
            height: 54,
            width: 184,
            child: ElevatedButton(
              onPressed: _isSubmitting
                  ? null
                  : () {
                      if (_formKey.currentState!.validate()) {
                        _formKey.currentState!.save();
                        loginUser(email!, password!);
                      }
                    },
              style: ElevatedButton.styleFrom(
                backgroundColor: primaryColor,
                shape: const RoundedRectangleBorder(
                  borderRadius: BorderRadius.all(Radius.circular(24.0)),
                ),
              ),
              child: _isSubmitting
                  ? const SizedBox(
                      width: 24,
                      height: 24,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text(
                      'Login',
                      style: TextStyle(fontSize: 24, color: Colors.white),
                    ),
            ),
          ),
        ],
      ),
    );
  }
}
