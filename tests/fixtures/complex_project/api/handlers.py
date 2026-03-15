"""API handlers demonstrating cross-module call chains."""

from ..core import BaseProcessor, Registry
from ..core.base import JSONProcessor


def handle_request(request_data):
    result = Registry.process("json", request_data)
    return format_response(result)


def format_response(data):
    return {"status": "ok", "data": data}


class CustomProcessor(BaseProcessor):
    """Processor defined in a different module, extending core base."""

    def process(self, data):
        return {"custom": data}


async def async_handler(data):
    """Async handler to test async function extraction."""
    processor = JSONProcessor()
    return processor.run(data)
