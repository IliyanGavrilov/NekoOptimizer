from django.contrib import admin

from planner.models import Cat, Seed


@admin.register(Cat)
class CatAdmin(admin.ModelAdmin):
    list_display = ("name", "rarity", "owned", "wanted")
    list_filter = ("rarity", "owned", "wanted")
    search_fields = ("name",)


admin.site.register(Seed)
