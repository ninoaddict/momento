import time
from functools import wraps
from beartype.typing import Any, Callable, Optional, TypeVar, cast

T = TypeVar("T", bound=Callable[..., Any])


def exponential_backoff(retries: int = 5, base_wait_time: int = 1) -> Callable[[T], T]:
    """Decorator for applying exponential backoff to a function.

    Args:
        retries: Maximum number of attempts (including the first).
        base_wait_time: Base wait time in seconds; actual wait for attempt
            ``n`` is ``base_wait_time * 2 ** n``.
    """

    def decorator(func: T) -> T:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[Exception] = None
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    wait_time = base_wait_time * (2 ** attempt)
                    print(
                        f"Attempt {attempt + 1}/{retries} for '{func.__name__}' "
                        f"failed: {exc}"
                    )
                    if attempt < retries - 1:
                        print(f"Retrying in {wait_time}s...")
                        time.sleep(wait_time)
            print(f"All {retries} retries for '{func.__name__}' exhausted.")
            raise last_exc  # type: ignore[misc]

        return cast(T, wrapper)

    return cast(Callable[[T], T], decorator)
