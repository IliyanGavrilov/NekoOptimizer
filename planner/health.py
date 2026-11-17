from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from django.http import HttpResponse

LIVE = "/livez"
READY = "/readyz"


def _text(body: str, status: int = 200) -> HttpResponse:
    return HttpResponse(body, status=status, content_type="text/plain")


class _Schema:
    """Whether the database has every migration this code ships. Once it has, it stays so
    for the life of the process (a newer schema arrives only with newer code), so the
    migration graph is walked only until the first yes."""

    current = False

    @classmethod
    def check(cls) -> bool:
        if not cls.current:
            executor = MigrationExecutor(connection)
            cls.current = not executor.migration_plan(executor.loader.graph.leaf_nodes())
        return cls.current


def probes(get_response):
    """Answer Kubernetes' liveness and readiness probes ahead of every other middleware.

    The kubelet probes a pod by its IP over plain HTTP, so further down the stack the Host
    check would reject it (a pod IP is no allowed host) and the HTTPS redirect would bounce
    it. Liveness says only that the process answers - it must not touch the database, or a
    database outage would have Kubernetes restart every healthy pod. Readiness also wants
    the database reachable and migrated to this code's schema: a pod short of either is
    kept out of the Service, so a rollout's new pods take no traffic until the migrate Job
    has run, and the old ones go on serving meanwhile."""

    def middleware(request):
        if request.path == LIVE:
            return _text("ok")
        if request.path == READY:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                migrated = _Schema.check()
            except DatabaseError:
                return _text("database unavailable", status=503)
            if not migrated:
                return _text("migrations pending", status=503)
            return _text("ok")

        return get_response(request)

    return middleware
