import pytest
from django.db import OperationalError
from django.test import override_settings

# How the kubelet probes a pod: by its IP, over plain HTTP, against a production setup.
PROBE = {"HTTP_HOST": "10.244.0.7:8000"}
PRODUCTION = override_settings(ALLOWED_HOSTS=["neko.example"], SECURE_SSL_REDIRECT=True)


@PRODUCTION
def test_liveness_answers_a_probe_by_pod_ip_over_http(client):
    response = client.get("/livez", **PROBE)
    assert (response.status_code, response.content) == (200, b"ok")


@PRODUCTION
@pytest.mark.django_db
def test_readiness_answers_when_the_database_does(client):
    assert client.get("/readyz", **PROBE).status_code == 200


@PRODUCTION
def test_readiness_fails_while_the_database_is_unreachable(client, monkeypatch):
    def down():
        raise OperationalError("connection refused")

    monkeypatch.setattr("planner.health.connection.cursor", down)
    assert client.get("/readyz", **PROBE).status_code == 503


@PRODUCTION
@pytest.mark.django_db
def test_readiness_fails_until_the_schema_is_migrated(client, monkeypatch):
    monkeypatch.setattr("planner.health._Schema.current", False)
    monkeypatch.setattr(
        "planner.health.MigrationExecutor.migration_plan", lambda self, targets: ["pending"]
    )
    response = client.get("/readyz", **PROBE)
    assert (response.status_code, response.content) == (503, b"migrations pending")


@PRODUCTION
def test_liveness_never_asks_the_database(client, monkeypatch):
    def down():
        raise OperationalError("connection refused")

    monkeypatch.setattr("planner.health.connection.cursor", down)
    assert client.get("/livez", **PROBE).status_code == 200
