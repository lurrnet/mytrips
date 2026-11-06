"""P0 regression: database setting cannot override SMTP listener shutdown."""
def test_smtp_disabled_by_deployment_policy_even_if_admin_enables(monkeypatch):
    from backend import database, smtp_server
    from backend.config import settings
    monkeypatch.setattr(settings, "DISABLE_SMTP_SERVER", True)
    def unexpected_database_read(*_args, **_kwargs):
        raise AssertionError("SMTP-disabled deployments must never query SMTP settings")
    monkeypatch.setattr(database, "get_global_setting", unexpected_database_read)
    smtp_server.start_smtp_server()
