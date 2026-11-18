import json
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from planner.models import SubmittedPage
from planner.views import sitemap_pages

ENDPOINT = "https://api.indexnow.org/indexnow"


class Command(BaseCommand):
    help = "Tell IndexNow search engines (Bing, Yandex, Naver, ...) the new or changed pages."

    def handle(self, *args, **options):
        key = settings.INDEXNOW_KEY
        if not key:
            raise CommandError("INDEXNOW_KEY is not set.")
        sent = dict(SubmittedPage.objects.values_list("loc", "lastmod"))
        pages = [
            page for page in sitemap_pages() if sent.get(page["loc"]) != page.get("lastmod", "")
        ]
        if not pages:
            self.stdout.write("No new or changed pages to submit.")
            return
        site = settings.SITE_URL
        body = {
            "host": urlsplit(site).hostname,
            "key": key,
            "keyLocation": f"{site}{reverse('indexnow_key', args=[key])}",
            "urlList": [f"{site}{page['loc']}" for page in pages],
        }
        request = Request(
            ENDPOINT,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        with urlopen(request, timeout=30) as response:  # nosec B310
            SubmittedPage.objects.bulk_create(
                [SubmittedPage(loc=page["loc"], lastmod=page.get("lastmod", "")) for page in pages],
                update_conflicts=True,
                unique_fields=["loc"],
                update_fields=["lastmod"],
            )
            self.stdout.write(
                self.style.SUCCESS(f"IndexNow answered {response.status} for {len(pages)} URLs.")
            )
