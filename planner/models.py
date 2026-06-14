from django.db import models


class CatQuerySet(models.QuerySet):
    def unowned(self) -> CatQuerySet:
        return self.filter(owned=False)

    def wishlist(self) -> CatQuerySet:
        return self.filter(wanted=True, owned=False)


class Cat(models.Model):
    """A cat in the catalogue, with the player's ownership and wishlist flags."""

    name = models.CharField(max_length=200, unique=True)
    rarity = models.CharField(max_length=20, blank=True)
    owned = models.BooleanField(default=False)
    wanted = models.BooleanField(default=False)

    objects = CatQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Seed(models.Model):
    """The shared gacha seed, persisted as a single row across sessions."""

    value = models.BigIntegerField()

    @classmethod
    def current(cls) -> int | None:
        row = cls.objects.first()
        return row.value if row else None

    @classmethod
    def store(cls, value: int) -> None:
        cls.objects.update_or_create(pk=1, defaults={"value": value})
