from django.contrib import admin

from planner.models import Cat, Profile, Seed, Unit


# These lists show the region the site is switched to, like every other page: the
# models' default manager is scoped to it.
@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("unit_id", "name", "rarity", "canonical")
    list_filter = ("rarity", "canonical")
    search_fields = ("name",)


@admin.register(Cat)
class CatAdmin(admin.ModelAdmin):
    list_display = ("name", "rarity", "unit")
    list_filter = ("rarity",)
    search_fields = ("name",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("__str__", "region", "created")
    list_filter = ("region",)
    search_fields = ("user__username",)
    fields = ("user", "region", "created")
    readonly_fields = ("created",)


admin.site.register(Seed)
