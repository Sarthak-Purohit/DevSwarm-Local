class Calculator:
    """A simple calculator demonstrating classes, docstrings, and methods."""

    def add(self, a, b):
        return a + b

    def divide(self, a: float, b: float = 1.0) -> float:
        if b == 0:
            raise ValueError("Cannot divide by zero.")
        return a / b


def greet(name):
    return f"Hello, {name}!"


async def fetch_data(url: str) -> dict:
    return {"url": url, "status": "ok"}
