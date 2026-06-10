from __future__ import annotations


class HelloWorld:

    def __init__(self, name: str, count: int) -> None:
        self.name = name
        self.count = count

    def get_name(self) -> str:
        return self.name

    def set_name(self, name: str) -> None:
        self.name = name

    def greet_all(self, people: list[str]) -> list[str]:
        greetings: list[str] = []
        for person in people:
            greetings.append(f"Hello, {person}!")
        return greetings

    @staticmethod
    def main(args: list[str]) -> None:
        hw = HelloWorld("World", 1)
        print(hw.get_name())
