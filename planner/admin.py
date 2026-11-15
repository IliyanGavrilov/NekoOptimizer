from django.contrib import admin

from planner.catalogue_cache import bump_catalogue
from planner.models import Cat, Profile, Seed, Unit


class CatalogueAdmin(admin.ModelAdmin):
    """An edit here changes the catalogue every server process keeps in memory."""

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        bump_catalogue()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        bump_catalogue()

    def delete_queryset(self, request, queryset):
        super().delete_queryset(request, queryset)
        bump_catalogue()


# These lists show the region the site is switched to, like every other page: the
# models' default manager is scoped to it.
@admin.register(Unit)
class UnitAdmin(CatalogueAdmin):
    list_display = ("unit_id", "name", "rarity", "canonical")
    list_filter = ("rarity", "canonical")
    search_fields = ("name",)


@admin.register(Cat)
class CatAdmin(CatalogueAdmin):
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
