from functools import wraps
from time import time


class SimpleCache:
    def __init__(self):
        self._cache = {}

    def set(self, key, value, ttl=None):
        if ttl is None:
            self._cache[key] = (value, None)
        else:
            self._cache[key] = (value, time() + ttl)

    def get(self, key):
        if key in self._cache:
            value, expiry = self._cache[key]
            if expiry is None or time() < expiry:
                return value
            else:
                del self._cache[key]
        return None

    def delete(self, key):
        if key in self._cache:
            del self._cache[key]


cache = SimpleCache()


def cached(ttl=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{func.__name__}:{args}:{kwargs}"
            result = cache.get(key)
            if result is None:
                result = func(*args, **kwargs)
                cache.set(key, result, ttl)
            return result

        return wrapper

    return decorator
