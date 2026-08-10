import 'dart:convert';
import 'package:flutter/material.dart';

import 'constants.dart';
import 'routePage.dart';

class Signup extends StatelessWidget {
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
                height: 85,
                width: 110,
                decoration: const BoxDecoration(
                  image: DecorationImage(
                      image: AssetImage('assets/SharpShooter.png'), fit: BoxFit.cover),
                ),
              ),
            )
          ],
        ),
      ),
      body: SingleChildScrollView(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: <Widget>[
            const SizedBox(height: 50),
            Text(appName,
                textAlign: TextAlign.center,
                style: const TextStyle(
                    fontWeight: FontWeight.bold, fontSize: 30)),
            Padding(
              padding: const EdgeInsets.all(8.0),
              child: SignupForm(),
            ),
            Padding(
              padding: const EdgeInsets.all(15.0),
              child: Row(
                children: <Widget>[
                  const Text('Already here  ?',
                      style:
                      TextStyle(fontWeight: FontWeight.bold, fontSize: 20)),
                  GestureDetector(
                    onTap: () {
                      Navigator.pop(context);
                    },
                    child: const Text(' Get Logged in Now!',
                        style: TextStyle(fontSize: 20, color: Colors.blue)),
                  )
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class SignupForm extends StatefulWidget {
  SignupForm({Key? key}) : super(key: key);

  @override
  _SignupFormState createState() => _SignupFormState();
}

class _SignupFormState extends State<SignupForm> {
  final _formKey = GlobalKey<FormState>();

  String? email;
  String? password;
  bool _obscureText = false;
  bool agree = false;
  final pass = TextEditingController();

  // Helper method to register a user
  Future<void> registerUser(String email, String password) async {
    const String apiUrl = "$backend_Url/register";

    try {
      final response = await customHttpClient.post(
        Uri.parse(apiUrl),
        headers: {"Content-Type": "application/json"},
        body: json.encode({"username": email, "password": password}),
      );

      if (response.statusCode == 200) {
        final result = json.decode(response.body);
        user_id = result["user_id"];
        id_token = result["idToken"];
        if (!mounted) return;
        // Registration returns a valid Firebase session, so no second login is needed.
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(builder: (context) => const RouteVolunteerPage()),
        );
      } else {
        final error = json.decode(response.body)["error"];
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(
            error ?? "An error occurred. Please try again.",
            style: const TextStyle(fontSize: 16),
          ),
        ));
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(
          "Error: $e",
          style: const TextStyle(fontSize: 16),
        ),
      ));
    }
  }

  @override
  Widget build(BuildContext context) {
    var border = const OutlineInputBorder(
      borderRadius: BorderRadius.all(
        Radius.circular(100.0),
      ),
    );

    var space = const SizedBox(height: 10);
    return Form(
      key: _formKey,
      child: Column(
        children: <Widget>[
          // Email
          TextFormField(
            decoration: InputDecoration(
                prefixIcon: const Icon(Icons.email_outlined),
                labelText: 'Email',
                border: border),
            validator: (value) {
              if (value!.isEmpty) {
                return 'Please enter some text';
              }
              return null;
            },
            onSaved: (val) {
              email = val;
            },
            keyboardType: TextInputType.emailAddress,
          ),
          space,
          // Password
          TextFormField(
            controller: pass,
            decoration: InputDecoration(
              labelText: 'Password',
              prefixIcon: const Icon(Icons.lock_outline),
              border: border,
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
            onSaved: (val) {
              password = val;
            },
            obscureText: !_obscureText,
            validator: (value) {
              if (value!.isEmpty) {
                return 'Please enter some text';
              }
              return null;
            },
          ),
          space,
          // Confirm Password
          TextFormField(
            decoration: InputDecoration(
              labelText: 'Confirm Password',
              prefixIcon: const Icon(Icons.lock_outline),
              border: border,
            ),
            obscureText: true,
            validator: (value) {
              if (value != pass.text) {
                return 'Passwords do not match';
              }
              return null;
            },
          ),
          space,
          // Terms and Conditions
          Row(
            children: <Widget>[
              Expanded(
                flex: 1,
                child: Checkbox(
                  onChanged: (_) {
                    setState(() {
                      agree = !agree;
                    });
                  },
                  value: agree,
                ),
              ),
              const Expanded(
                flex: 4,
                child: Text(
                    'By creating an account, I agree to Terms & Conditions and Privacy Policy.'),
              ),
            ],
          ),
          const SizedBox(height: 10),
          // Sign Up Button
          SizedBox(
            height: 50,
            width: double.infinity,
            child: ElevatedButton(
              onPressed: () {
                if (_formKey.currentState!.validate() && agree) {
                  _formKey.currentState!.save();
                  registerUser(email!, password!);
                } else if (!agree) {
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                    content: Text(
                      "You must agree to the Terms & Conditions to proceed.",
                      style: TextStyle(fontSize: 16),
                    ),
                  ));
                }
              },
              style: ElevatedButton.styleFrom(
                  backgroundColor: primaryColor,
                  shape: const RoundedRectangleBorder(
                      borderRadius: BorderRadius.all(Radius.circular(24.0)))),
              child: const Text(
                'Sign Up',
                style: TextStyle(color: Colors.white),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
