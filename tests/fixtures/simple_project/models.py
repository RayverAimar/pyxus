"""Simple models for testing symbol extraction and inheritance."""


class Base:
    def save(self):
        pass

    def delete(self):
        pass


class User(Base):
    def __init__(self, name):
        self.name = name

    @property
    def display_name(self):
        return self.name.upper()

    @staticmethod
    def create(name):
        user = User(name)
        user.save()
        return user

    @classmethod
    def from_dict(cls, data):
        return cls(data["name"])
