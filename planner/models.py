import secrets

from django.conf import settings
from django.db import models

from neko.guidedata import load_guide
from neko.region import DEFAULT_REGION
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
    """A Battle Cats unit. Canonical units come from the game-data catalogue (keyed by
    PONOS id); provisional ones stand in for cats not yet in the catalogue, so ownership
    has a stable home that survives re-imports."""

    region = _region_field()
    unit_id = models.PositiveIntegerField()
    name = models.CharField(max_length=200)
    rarity = models.CharField(max_length=20, blank=True)
    set_name = models.CharField(max_length=200, blank=True)
    forms = models.JSONField(default=list)
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
    """A cat as the gacha schedule names it, linked to its catalogue unit."""

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


def _new_key() -> str:
    return secrets.token_urlsafe(32)


class Profile(models.Model):
    """One player's own state - their collection, plans, seed and game version - while the
    catalogue stays shared. It starts anonymous, on a visitor's first change, and a cookie
    carries its key; signing up attaches a User, so it follows them to any device."""

    key = models.CharField(max_length=43, unique=True, default=_new_key)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    region = models.CharField(max_length=2, default=DEFAULT_REGION)
    owned = models.ManyToManyField(Unit, related_name="owned_by", blank=True)
    wanted = models.ManyToManyField(Unit, related_name="wanted_by", blank=True)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.user) if self.user else f"Guest {self.pk}"

    def units(self, mark: str) -> models.QuerySet:
        """The active region's units this player has marked ``mark`` ("owned" or "wanted")."""
        if self.pk is None:
            return Unit.objects.none()

        return getattr(self, mark).all()

    def wishlist(self) -> models.QuerySet:
        """Wanted units not owned yet - what a wishlist search goes after."""
        return self.units("wanted").exclude(pk__in=self.units("owned"))

    def marks(self) -> tuple[set[int], set[int]]:
        """The pks of the units this player owns and wants, for marking chips."""
        owned = set(self.units("owned").values_list("pk", flat=True))
        wanted = set(self.units("wanted").values_list("pk", flat=True))

        return owned, wanted


class UnitPlan(models.Model):
    """A unit on the player's resources list. The row is the cat's place on the list -
    it stays put with nothing ticked - and the flags are the evolutions they're grinding
    for; the talents they want are TalentPlan rows hanging off the same unit."""

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="unit_plans")
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="plans")
    tf = models.BooleanField(default=False)
    uf = models.BooleanField(default=False)

    objects = UnitPlanManager()
    all_regions = models.Manager()

    class Meta:
        base_manager_name = "all_regions"
        constraints = [models.UniqueConstraint(fields=("profile", "unit"), name="unique_unit_plan")]

    def __str__(self) -> str:
        return f"{self.unit} evolve plan"


class TalentPlan(models.Model):
    """One talent the player wants to buy: the unit and the slot's index in the
    committed talents document."""

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="talent_plans")
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="talent_plans")
    slot = models.PositiveSmallIntegerField()

    objects = UnitPlanManager()
    all_regions = models.Manager()

    class Meta:
        base_manager_name = "all_regions"
        constraints = [
            models.UniqueConstraint(
                fields=("profile", "unit", "slot"), name="unique_talent_plan_slot"
            )
        ]

    def __str__(self) -> str:
        return f"{self.unit} talent {self.slot}"


class CannonPlan(models.Model):
    """One Cat Base development being tracked: the level each part sits at now. The
    cannon comes with the row; its matching Foundation and Style are add-ons, tracked
    only once switched on (they cost Z Materials, a grind of their own)."""

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="cannon_plans")
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
            models.UniqueConstraint(
                fields=("profile", "region", "cannon_id"), name="unique_cannon_per_region"
            )
        ]

    def __str__(self) -> str:
        return f"Cannon {self.cannon_id} plan"


class Seed(models.Model):
    """A player's gacha seed, one row per game version (an account per version)."""

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="seeds")
    region = _region_field()
    value = models.BigIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("profile", "region"), name="unique_seed_per_region")
        ]

    @classmethod
    def store(cls, profile: Profile, value: int) -> None:
        cls.objects.update_or_create(
            profile=profile, region=active_region(), defaults={"value": value}
        )
