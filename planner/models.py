from django.db import models


class CatQuerySet(models.QuerySet):
    def unowned(self) -> CatQuerySet:
        return self.filter(owned=False)

    def wishlist(self) -> CatQuerySet:
        return self.filter(wanted=True, owned=False)


class Unit(models.Model):
    """A canonical Battle Cats unit from the game-data catalogue, keyed by its PONOS id."""

    unit_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=200)
    rarity = models.CharField(max_length=20, blank=True)
    forms = models.JSONField(default=list)

    class Meta:
        ordering = ["unit_id"]

    def __str__(self) -> str:
        return self.name


class Banner(models.Model):
    """A gacha banner, identified by its recurring name; cats accumulate across re-runs."""

    name = models.CharField(max_length=200, unique=True)
    start = models.DateField(null=True, blank=True)
    end = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Cat(models.Model):
    """A cat in the catalogue, with the player's ownership and wishlist flags."""

    name = models.CharField(max_length=200, unique=True)
    rarity = models.CharField(max_length=20, blank=True)
    owned = models.BooleanField(default=False)
    wanted = models.BooleanField(default=False)
    unit = models.ForeignKey(
        "Unit", null=True, blank=True, on_delete=models.SET_NULL, related_name="cats"
    )
    banners = models.ManyToManyField(Banner, related_name="cats", blank=True)

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
