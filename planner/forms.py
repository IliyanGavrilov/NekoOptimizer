from django import forms

from planner.models import Cat


class PlannerForm(forms.Form):
    seed = forms.IntegerField(min_value=0)
    tickets = forms.IntegerField(min_value=0, initial=0)
    catfood = forms.IntegerField(min_value=0, initial=0)
    targets = forms.ModelMultipleChoiceField(
        queryset=Cat.objects.unowned(), widget=forms.CheckboxSelectMultiple
    )
