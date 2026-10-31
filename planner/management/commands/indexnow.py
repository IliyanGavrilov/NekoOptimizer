import json
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from planner.views import sitemap_pages

ENDPOINT = "https://api.indexnow.org/indexnow"


class Command(BaseCommand):
    help = "Tell IndexNow search engines (Bing, Yandex, Naver, ...) every sitemap URL."

    def handle(self, *args, **options):
        key = settings.INDEXNOW_KEY
        if not key:
            raise CommandError("INDEXNOW_KEY is not set.")
        site = settings.SITE_URL
        urls = [f"{site}{page['loc']}" for page in sitemap_pages()]
        body = {
            "host": urlsplit(site).hostname,
            "key": key,
            "keyLocation": f"{site}{reverse('indexnow_key', args=[key])}",
            "urlList": urls,
        }
        request = Request(
            ENDPOINT,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        with urlopen(request, timeout=30) as response:  # nosec B310
            self.stdout.write(
                self.style.SUCCESS(f"IndexNow answered {response.status} for {len(urls)} URLs.")
            )
