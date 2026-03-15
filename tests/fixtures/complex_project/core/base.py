"""Abstract base classes demonstrating deep inheritance."""

from abc import ABC, abstractmethod


class BaseProcessor(ABC):
    @abstractmethod
    def process(self, data):
        pass

    def validate(self, data):
        if not data:
            raise ValueError("Empty data")
        return True

    def run(self, data):
        self.validate(data)
        return self.process(data)


class TransformProcessor(BaseProcessor):
    """Intermediate class in a 3-level hierarchy."""

    def transform(self, data):
        return str(data)

    def process(self, data):
        return self.transform(data)


class JSONProcessor(TransformProcessor):
    """Leaf class — 3 levels deep: BaseProcessor → TransformProcessor → JSONProcessor."""

    def transform(self, data):
        import json

        return json.dumps(data)
