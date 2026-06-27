from django import forms

from planner.models import Cat


class CatForm(forms.ModelForm):
    class Meta:
        model = Cat
        fields = ["name", "rarity"]


class PlannerForm(forms.Form):
    seed = forms.IntegerField(min_value=0)
    tickets = forms.IntegerField(min_value=0, initial=0)
    catfood = forms.IntegerField(min_value=0, initial=0)
    targets = forms.ModelMultipleChoiceField(
        queryset=Cat.objects.none(), required=False, widget=forms.CheckboxSelectMultiple
    )
    use_wishlist = forms.BooleanField(
        required=False, label="Also search my wishlist (unowned cats I marked wanted)"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["targets"].queryset = Cat.objects.unowned()

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
