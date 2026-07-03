from django.db import models

# Conjure/unreleased units have no name yet - it just echoes their id, e.g. "861_1".
_NO_REAL_NAME = r"^[0-9]+[-_][0-9]+$"


class UnitQuerySet(models.QuerySet):
    def wishlist(self) -> UnitQuerySet:
        return self.filter(wanted=True, owned=False)

    def named(self) -> UnitQuerySet:
        """Only units with a real display name (excludes conjure/unreleased id-name stand-ins)."""
        return self.exclude(name__regex=_NO_REAL_NAME)

    def unnamed(self) -> UnitQuerySet:
        """The conjure/unreleased units whose name is still just their id."""
        return self.filter(name__regex=_NO_REAL_NAME)


class Unit(models.Model):
    """A Battle Cats unit and the player's ownership of it. Canonical units come from the
    game-data catalogue (keyed by PONOS id); provisional ones stand in for cats not yet in
    the catalogue, so ownership has a stable home that survives re-imports."""

    unit_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=200)
    rarity = models.CharField(max_length=20, blank=True)
    set_name = models.CharField(max_length=200, blank=True)
    forms = models.JSONField(default=list)
    owned = models.BooleanField(default=False)
    wanted = models.BooleanField(default=False)
    canonical = models.BooleanField(default=True)

    objects = UnitQuerySet.as_manager()

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
    unit = models.ForeignKey(
        "Unit", null=True, blank=True, on_delete=models.SET_NULL, related_name="cats"
    )
    banners = models.ManyToManyField(Banner, related_name="cats", blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def owned(self) -> bool:
        return bool(self.unit and self.unit.owned)

    @property
    def wanted(self) -> bool:
        return bool(self.unit and self.unit.wanted)


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
