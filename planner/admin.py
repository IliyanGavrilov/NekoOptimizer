from django.contrib import admin

from planner.models import Cat, Region, Seed, Unit


# These lists show the region the site is switched to, like every other page: the
# models' default manager is scoped to it.
@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("unit_id", "name", "rarity", "owned", "wanted", "canonical")
    list_filter = ("rarity", "owned", "wanted", "canonical")
    search_fields = ("name",)


@admin.register(Cat)
class CatAdmin(admin.ModelAdmin):
    list_display = ("name", "rarity", "owned", "wanted")
    list_filter = ("rarity",)
    search_fields = ("name",)


admin.site.register(Seed)
admin.site.register(Region)
