import json

import pytest
from django.core.management import CommandError, call_command

from planner.models import SubmittedPage

SITE = "https://neko.example"


class _Response:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _pages():
    return [{"loc": "/"}, {"loc": "/jp/tiers/", "lastmod": "2026-10-01"}]


@pytest.fixture
def sent(monkeypatch, settings, db):
    """The JSON body of every request the command sends, with the network stubbed out."""
    settings.SITE_URL = SITE
    settings.INDEXNOW_KEY = "abc123key"
    bodies = []

    def urlopen(request, timeout):
        bodies.append(json.loads(request.data))
        return _Response()

    monkeypatch.setattr("planner.management.commands.indexnow.urlopen", urlopen)
    monkeypatch.setattr("planner.management.commands.indexnow.sitemap_pages", _pages)

    return bodies


def test_every_sitemap_page_is_submitted_under_the_site_url(sent):
    call_command("indexnow")
    assert sent[0]["urlList"] == [f"{SITE}/", f"{SITE}/jp/tiers/"]


def test_the_submission_names_the_host_and_where_the_key_lives(sent):
    call_command("indexnow")
    assert (sent[0]["host"], sent[0]["keyLocation"]) == ("neko.example", f"{SITE}/abc123key.txt")


def test_nothing_is_sent_without_a_key(sent, settings):
    settings.INDEXNOW_KEY = ""
    with pytest.raises(CommandError):
        call_command("indexnow")


def test_a_page_already_submitted_unchanged_is_left_out(sent):
    SubmittedPage.objects.create(loc="/")
    call_command("indexnow")
    assert sent[0]["urlList"] == [f"{SITE}/jp/tiers/"]


def test_a_page_whose_lastmod_moved_is_submitted_again(sent):
    SubmittedPage.objects.create(loc="/")
    SubmittedPage.objects.create(loc="/jp/tiers/", lastmod="2026-09-01")
    call_command("indexnow")
    assert sent[0]["urlList"] == [f"{SITE}/jp/tiers/"]


def test_a_second_run_with_nothing_changed_sends_nothing(sent):
    call_command("indexnow")
    call_command("indexnow")
    assert len(sent) == 1
