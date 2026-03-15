"""Service layer that calls model methods."""

from models import User


class UserService:
    @staticmethod
    def create_user(name):
        return User.create(name)

    @staticmethod
    def get_display(user):
        return user.display_name


def process_user(user):
    """Top-level function that calls an instance method."""
    user.save()
    return user
