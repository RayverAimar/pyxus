"""Utility functions used across the project."""


def validate_name(name):
    if not name or not isinstance(name, str):
        raise ValueError("Invalid name")
    return name.strip()


def format_output(data):
    return str(data)
