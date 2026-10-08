from django.db import models

from neko.guidedata import load_guide
from neko.region import CODES, DEFAULT_REGION
from neko.region import current as active_region

# Conjure/unreleased units have no name yet - it just echoes their id, e.g. "861_1".
_NO_REAL_NAME = r"^[0-9]+[-_][0-9]+$"


def _region_field() -> models.CharField:
    """The column every per-version table carries; new rows land in the active region."""
    return models.CharField(max_length=2, default=active_region)


class RegionManager(models.Manager):
    """Default manager scoped to the active region (see neko.region). Each game version
    ships its own catalogue - different units, different names - so their rows live side
    by side and no view may mix them. ``all_regions`` is the unscoped way in."""

    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset().filter(region=active_region())


class UnitPlanManager(models.Manager):
    """Default manager for the plans hanging off a unit: scoped through that FK, since
    the unit row already belongs to exactly one region."""

    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset().filter(unit__region=active_region())


class UnitQuerySet(models.QuerySet):
    def wishlist(self) -> UnitQuerySet:
        return self.filter(wanted=True, owned=False)

    def named(self) -> UnitQuerySet:
        """Only units with a real display name (excludes conjure/unreleased id-name stand-ins)."""
        return self.exclude(name__regex=_NO_REAL_NAME)

    def unnamed(self) -> UnitQuerySet:
        """The conjure/unreleased units whose name is still just their id."""
        return self.filter(name__regex=_NO_REAL_NAME)

    def in_guide(self) -> UnitQuerySet:
        """Only the units this region's in-game Cat Guide lists. Every region ships the
        same unit table, so a catalogue carries units its players can never get - EN's
        holds Droid Cat and the other Japan-only promos - and the Cat Guide is the game's
        own statement of what a region actually has. Filtering is limited to the default
        region: guidedata resolves the wiki's English names against THAT catalogue, so
        the other regions' lists silently drop every unit it lacks (see its refresh())."""
        listed = load_guide()["regions"].get(active_region(), [])
        if not listed or active_region() != DEFAULT_REGION:
            return self
        return self.filter(unit_id__in=listed)


class Unit(models.Model):
    """A Battle Cats unit and the player's ownership of it. Canonical units come from the
    game-data catalogue (keyed by PONOS id); provisional ones stand in for cats not yet in
    the catalogue, so ownership has a stable home that survives re-imports."""

    region = _region_field()
    unit_id = models.PositiveIntegerField()
    name = models.CharField(max_length=200)
    rarity = models.CharField(max_length=20, blank=True)
    set_name = models.CharField(max_length=200, blank=True)
    forms = models.JSONField(default=list)
    owned = models.BooleanField(default=False)
    wanted = models.BooleanField(default=False)
    canonical = models.BooleanField(default=True)

    objects = RegionManager.from_queryset(UnitQuerySet)()
    all_regions = UnitQuerySet.as_manager()

    class Meta:
        ordering = ["unit_id"]
        base_manager_name = "all_regions"
        constraints = [
            models.UniqueConstraint(fields=("region", "unit_id"), name="unique_unit_per_region")
        ]

    def __str__(self) -> str:
        return self.name


class Banner(models.Model):
    """A gacha banner, identified by its recurring name; cats accumulate across re-runs."""

    region = _region_field()
    name = models.CharField(max_length=200)
    start = models.DateField(null=True, blank=True)
    end = models.DateField(null=True, blank=True)

    objects = RegionManager()
    all_regions = models.Manager()

    class Meta:
        ordering = ["name"]
        base_manager_name = "all_regions"
        constraints = [
            models.UniqueConstraint(fields=("region", "name"), name="unique_banner_per_region")
        ]

    def __str__(self) -> str:
        return self.name


class Cat(models.Model):
    """A cat in the catalogue, with the player's ownership and wishlist flags."""

    region = _region_field()
    name = models.CharField(max_length=200)
    rarity = models.CharField(max_length=20, blank=True)
    unit = models.ForeignKey(
        "Unit", null=True, blank=True, on_delete=models.SET_NULL, related_name="cats"
    )
    banners = models.ManyToManyField(Banner, related_name="cats", blank=True)

    objects = RegionManager()
    all_regions = models.Manager()

    class Meta:
        ordering = ["name"]
        base_manager_name = "all_regions"
        constraints = [
            models.UniqueConstraint(fields=("region", "name"), name="unique_cat_per_region")
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def owned(self) -> bool:
        return bool(self.unit and self.unit.owned)

    @property
    def wanted(self) -> bool:
        return bool(self.unit and self.unit.wanted)


class UnitPlan(models.Model):
    """A unit on the player's resources list. The row is the cat's place on the list -
    it stays put with nothing ticked - and the flags are the evolutions they're grinding
    for; the talents they want are TalentPlan rows hanging off the same unit."""

    unit = models.OneToOneField(Unit, on_delete=models.CASCADE, related_name="plan")
    tf = models.BooleanField(default=False)
    uf = models.BooleanField(default=False)

    objects = UnitPlanManager()
    all_regions = models.Manager()

    class Meta:
        base_manager_name = "all_regions"

    def __str__(self) -> str:
        return f"{self.unit} evolve plan"


class TalentPlan(models.Model):
    """One talent the player wants to buy: the unit and the slot's index in the
    committed talents document."""

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="talent_plans")
    slot = models.PositiveSmallIntegerField()

    objects = UnitPlanManager()
    all_regions = models.Manager()

    class Meta:
        base_manager_name = "all_regions"
        constraints = [
            models.UniqueConstraint(fields=("unit", "slot"), name="unique_talent_plan_slot")
        ]

    def __str__(self) -> str:
        return f"{self.unit} talent {self.slot}"


class CannonPlan(models.Model):
    """One Cat Base development being tracked: the level each part sits at now. The
    cannon comes with the row; its matching Foundation and Style are add-ons, tracked
    only once switched on (they cost Z Materials, a grind of their own)."""

    region = _region_field()
    cannon_id = models.PositiveSmallIntegerField()
    cannon_now = models.PositiveSmallIntegerField(default=0)
    base_now = models.PositiveSmallIntegerField(default=0)
    deco_now = models.PositiveSmallIntegerField(default=0)
    base_on = models.BooleanField(default=False)
    deco_on = models.BooleanField(default=False)

    objects = RegionManager()
    all_regions = models.Manager()

    class Meta:
        base_manager_name = "all_regions"
        constraints = [
            models.UniqueConstraint(fields=("region", "cannon_id"), name="unique_cannon_per_region")
        ]

    def __str__(self) -> str:
        return f"Cannon {self.cannon_id} plan"


class Seed(models.Model):
    """The gacha seed, persisted as one row per game version (an account per version)."""

    region = _region_field()
    value = models.BigIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=("region",), name="unique_seed_per_region")]

    @classmethod
    def current(cls) -> int | None:
        row = cls.objects.filter(region=active_region()).first()

        return row.value if row else None

    @classmethod
    def store(cls, value: int) -> None:
        cls.objects.update_or_create(region=active_region(), defaults={"value": value})


class Region(models.Model):
    """The game version the site is showing, persisted as a single row across sessions."""

    code = models.CharField(max_length=2, default=DEFAULT_REGION)

    @classmethod
    def current(cls) -> str:
        row = cls.objects.first()

        return row.code if row and row.code in CODES else DEFAULT_REGION

    @classmethod
    def store(cls, code: str) -> None:
        cls.objects.update_or_create(pk=1, defaults={"code": code})
