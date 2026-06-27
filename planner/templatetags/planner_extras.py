from django import template

register = template.Library()


@register.filter
def lookup(mapping, key):
    """Look a key up in a dict from a template, falling back to [key]."""
    if mapping and key in mapping:
        return mapping[key]
    return [key]
