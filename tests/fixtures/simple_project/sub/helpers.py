"""Helper functions in a sub-package, testing relative imports."""

from ..utils import validate_name


def compute(value):
    validated = validate_name(str(value))
    return len(validated)
