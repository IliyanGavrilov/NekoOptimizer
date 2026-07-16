from django import forms

from neko.models import CATFOOD_PER_DRAW
from planner.models import Cat, Unit

EXPLORE_HORIZON = 1000  # default rolls to look ahead per banner in explore mode
MAX_TRACK_LENGTH = 999  # godfat's unit-count ceiling for the Rolls table
MAX_FUTURE_UBERS = 99  # placeholder ubers the Rolls table will pad a pool with
# Observed pulls the seed finder accepts: below 5 the window rarely pins one seed
# down (the search truncates), and past 30 the extras stop adding information.
MIN_SEEK_ROLLS = 5
MAX_SEEK_ROLLS = 30


class PlannerForm(forms.Form):
    # A plain text box, not a number spinner: no native up/down arrows, and since app.js only
    # scrubs input[type=number], no hold-and-drag-to-nudge either - the seed is typed, never
    # stepped. inputmode keeps the mobile numeric keypad; it's still validated as an integer.
    seed = forms.IntegerField(
        min_value=0,
        initial=0,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "pattern": "[0-9]*"}),
    )
    # Optional: explore mode hides the budget, and a blank field just means zero.
    tickets = forms.IntegerField(min_value=0, initial=0, required=False)
    catfood = forms.IntegerField(min_value=0, initial=0, required=False)
    targets = forms.ModelMultipleChoiceField(
        queryset=Cat.objects.none(), required=False, widget=forms.CheckboxSelectMultiple
    )
    use_wishlist = forms.BooleanField(
        required=False, label="Also search my wishlist (unowned cats I marked wanted)"
    )
    ticket_value = forms.IntegerField(
        min_value=1,
        initial=CATFOOD_PER_DRAW,
        required=False,
        label="1 rare ticket is worth (catfood)",
    )
    platinum_cap = forms.IntegerField(
        min_value=0,
        initial=1,
        required=False,
        label="Platinum tickets",
    )
    legend_cap = forms.IntegerField(
        min_value=0,
        initial=1,
        required=False,
        label="Legend tickets",
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

    def clean_ticket_value(self):
        return self.cleaned_data.get("ticket_value") or CATFOOD_PER_DRAW

    def clean_platinum_cap(self):
        cap = self.cleaned_data.get("platinum_cap")

        return 1 if cap is None else cap

    def clean_legend_cap(self):
        cap = self.cleaned_data.get("legend_cap")

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
            and not Unit.objects.wishlist()
        ):
            raise forms.ValidationError("Your wishlist is empty - mark some cats as wanted first.")

        return cleaned
