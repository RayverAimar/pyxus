"""Registry pattern demonstrating inter-procedural calls."""


class Registry:
    _processors = {}  # noqa: RUF012

    @classmethod
    def register(cls, name, processor_cls):
        cls._processors[name] = processor_cls

    @classmethod
    def get(cls, name):
        return cls._processors.get(name)

    @classmethod
    def process(cls, name, data):
        processor_cls = cls.get(name)
        if processor_cls is None:
            raise KeyError(f"Unknown processor: {name}")
        processor = processor_cls()
        return processor.run(data)
