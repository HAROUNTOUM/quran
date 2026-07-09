from django import template

register = template.Library()


@register.filter
def has_role(user, role):
    return user.is_authenticated and user.role == role


@register.filter
def arabic_number(number):
    arabic_digits = "٠١٢٣٤٥٦٧٨٩"
    return "".join(arabic_digits[int(d)] if d.isdigit() else d for d in str(number))


@register.simple_tag
def unread_count(user):
    if not user.is_authenticated:
        return 0
    return user.notifications.filter(is_read=False).count()


@register.filter
def get_item(d, key):
    if not isinstance(d, dict):
        return None
    return d.get(key)


@register.filter
def index(lst, i):
    try:
        return lst[i]
    except (IndexError, TypeError):
        return None
