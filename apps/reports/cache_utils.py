from django.core.cache import cache


def cached(timeout=300):
    def decorator(func):
        def wrapper(*args, **kwargs):
            user_id = None
            for a in args:
                if hasattr(a, "user") and hasattr(a.user, "id"):
                    user_id = a.user.id
                    break
            key = f"dashboard:{func.__name__}:{user_id or 'anon'}:{hash(frozenset(kwargs.items()))}"
            result = cache.get(key)
            if result is not None:
                return result
            result = func(*args, **kwargs)
            cache.set(key, result, timeout)
            return result
        return wrapper
    return decorator
