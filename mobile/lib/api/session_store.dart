import 'api_models.dart';

class SessionStore {
  AuthSession? _session;
  int _revision = 0;

  AuthSession? get session => _session;
  String? get userId => _session?.userId;
  String? get idToken => _session?.idToken;
  String? get refreshToken => _session?.refreshToken;
  bool get isAuthenticated => _session != null;
  bool get canRefresh => _session?.canRefresh ?? false;
  bool get shouldRefresh => _session?.shouldRefresh ?? false;
  int get revision => _revision;

  void setSession(AuthSession session) {
    _session = session;
    _revision++;
  }

  bool clear() {
    final hadSession = _session != null;
    _session = null;
    _revision++;
    return hadSession;
  }
}
