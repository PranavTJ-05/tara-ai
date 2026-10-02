"""Small self-healing helpers: retry with backoff, and an ordered fallback chain."""
import functools
import logging
import time

log = logging.getLogger("tara")


def retry(attempts: int = 3, base_delay: float = 0.5):
    """Retry a sync function on any exception with exponential backoff."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            for i in range(attempts):
                try:
                    return fn(*a, **kw)
                except Exception as e:  # noqa: BLE001 - we re-raise on the last attempt
                    if i == attempts - 1:
                        raise
                    wait = base_delay * (2 ** i)
                    log.warning("%s failed (%s); retry %d/%d in %.1fs", fn.__name__, e, i + 1, attempts - 1, wait)
                    time.sleep(wait)
        return wrapper
    return deco


def first_success(candidates):
    """candidates: [(name, zero-arg callable)]. Returns (name, result) of the first that works."""
    errors = []
    for name, call in candidates:
        try:
            return name, call()
        except Exception as e:  # noqa: BLE001
            log.warning("provider %s failed: %s", name, e)
            errors.append(f"{name}: {e}")
    raise RuntimeError("all providers failed: " + "; ".join(errors))
