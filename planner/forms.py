import json

from django import forms

from neko.models import CATFOOD_PER_DRAW, is_future_uber
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
    # The future-uber placeholders toggled as targets: a JSON list of qualified names posted
    # by the legend chips. Not a real model field (they're pool padding, not catalogue units),
    # so it rides alongside ``targets`` and counts as a target for the "pick something" check.
    future_targets = forms.CharField(required=False)
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

    def clean_future_targets(self):
        """Parse the posted JSON list into the qualified placeholder names, dropping anything
        that isn't a future-uber placeholder (a stray post can't smuggle in a real name)."""
        try:
            data = json.loads(self.cleaned_data.get("future_targets") or "[]")
        except json.JSONDecodeError, TypeError:
            return []
        if not isinstance(data, list):
            return []

        return [str(name) for name in data if is_future_uber(str(name))]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""  # no trailing colons; required fields are marked with *
        self.fields["targets"].queryset = Cat.objects.all()

    def clean(self):
        cleaned = super().clean()
        # A future uber toggled on its own is a valid search, so it counts as a target here.
        has_target = cleaned.get("targets") or cleaned.get("future_targets")
        if not has_target and not cleaned.get("use_wishlist"):
            raise forms.ValidationError("Pick at least one target, or tick 'search my wishlist'.")
        if cleaned.get("use_wishlist") and not has_target and not Unit.objects.wishlist():
            raise forms.ValidationError("Your wishlist is empty - mark some cats as wanted first.")

        return cleaned
