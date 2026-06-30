from django import forms

from neko.models import CATFOOD_PER_DRAW
from planner.models import Cat

EXPLORE_HORIZON = 1000  # default rolls to look ahead per banner in explore mode


class CatForm(forms.ModelForm):
    class Meta:
        model = Cat
        fields = ["name", "rarity"]


class PlannerForm(forms.Form):
    seed = forms.IntegerField(min_value=0, initial=0)
    # Optional: explore mode hides the budget, and a blank field just means zero.
    tickets = forms.IntegerField(min_value=0, initial=0, required=False)
    catfood = forms.IntegerField(min_value=0, initial=0, required=False)
    targets = forms.ModelMultipleChoiceField(
        queryset=Cat.objects.none(), required=False, widget=forms.CheckboxSelectMultiple
    )
    use_wishlist = forms.BooleanField(
        required=False, label="Also search my wishlist (unowned cats I marked wanted)"
    )
    prefer = forms.ChoiceField(
        choices=[("tickets", "Rare tickets"), ("catfood", "Catfood")],
        initial="tickets",
        required=False,
        label="Prefer",
    )
    ticket_value = forms.IntegerField(
        min_value=1,
        initial=CATFOOD_PER_DRAW,
        required=False,
        label="1 rare ticket is worth (catfood)",
    )
    platinum_legend_cap = forms.IntegerField(
        min_value=0,
        initial=1,
        required=False,
        label="Platinum/Legend pulls allowed",
    )
    explore = forms.BooleanField(
        required=False,
        initial=True,
        label="Explore mode - Plan without a budget",
    )
    horizon = forms.IntegerField(
        min_value=1,
        initial=EXPLORE_HORIZON,
        required=False,
        label="Max depth (rolls)",
    )

    def clean_tickets(self):
        return self.cleaned_data.get("tickets") or 0

    def clean_catfood(self):
        return self.cleaned_data.get("catfood") or 0

    def clean_horizon(self):
        return self.cleaned_data.get("horizon") or EXPLORE_HORIZON

    def clean_prefer(self):
        return self.cleaned_data.get("prefer") or "tickets"

    def clean_ticket_value(self):
        return self.cleaned_data.get("ticket_value") or CATFOOD_PER_DRAW

    def clean_platinum_legend_cap(self):
        cap = self.cleaned_data.get("platinum_legend_cap")
        return 1 if cap is None else cap

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""  # no trailing colons; required fields are marked with *
        self.fields["targets"].queryset = Cat.objects.all()

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("targets") and not cleaned.get("use_wishlist"):
            raise forms.ValidationError("Pick at least one target, or tick 'search my wishlist'.")
        if (
            cleaned.get("use_wishlist")
            and not cleaned.get("targets")
            and not Cat.objects.wishlist()
        ):
            raise forms.ValidationError("Your wishlist is empty - mark some cats as wanted first.")
        return cleaned
