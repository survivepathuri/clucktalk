"""Domain errors. Each carries a customer-safe English message, and the tool layer turns it into the
structured MCP error (docs/DESIGN.md §5, rule 4). No codes, IDs, or JSON in the message."""

from __future__ import annotations


class DomainError(Exception):
    def __init__(self, customer_message: str, next_step: str) -> None:
        super().__init__(customer_message)
        self.customer_message = customer_message
        self.next_step = next_step


class UnknownHouse(DomainError):
    def __init__(self, reference: str, known_labels: list[str]) -> None:
        super().__init__(
            f"I couldn't find a shed called {reference}.",
            f"Your sheds are {', '.join(known_labels)}. Which one do you mean?",
        )
        self.reference = reference


class NoReferenceCurve(DomainError):
    def __init__(self, breed: str) -> None:
        super().__init__(
            f"I don't have a verified growth standard for {breed} yet, so I can't compare weight or feed to target.",
            "I can still tell you deaths and feed stock for this shed.",
        )
        self.breed = breed


class InsufficientData(DomainError):
    def __init__(self, what: str) -> None:
        super().__init__(
            f"I don't have enough recent records to work out {what}.",
            "Add today's readings for this shed, then ask me again.",
        )


class InvalidInput(DomainError):
    def __init__(self, customer_message: str, next_step: str) -> None:
        super().__init__(customer_message, next_step)
