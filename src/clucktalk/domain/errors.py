"""Domain errors. Each carries a customer-safe message and one next step, in English and Telugu; the tool layer
turns it into the structured MCP error (docs/DESIGN.md §5, rule 4). No codes, IDs, or JSON in the message.
Telugu is pending native-speaker review (clucktalk.i18n.TE_REVIEWED)."""

from __future__ import annotations


class DomainError(Exception):
    def __init__(self, customer_message: str, next_step: str, customer_message_te: str, next_step_te: str) -> None:
        super().__init__(customer_message)
        self.customer_message = customer_message
        self.next_step = next_step
        self.customer_message_te = customer_message_te
        self.next_step_te = next_step_te
        # Numbers the message speaks, so a card can show them too (cross-modal rule, docs/DESIGN.md §6).
        self.values: dict[str, float] = {}


class UnknownHouse(DomainError):
    def __init__(self, reference: str, known_labels: list[str], known_labels_te: list[str]) -> None:
        super().__init__(
            f"I couldn't find a shed called {reference}.",
            f"Your sheds are {', '.join(known_labels)}. Which one do you mean?",
            f"{reference} అనే షెడ్ నాకు కనబడలేదు.",
            f"మీ షెడ్లు: {', '.join(known_labels_te)}. మీరు ఏది అడుగుతున్నారు?",
        )
        self.reference = reference


class NoReferenceCurve(DomainError):
    def __init__(self, breed: str) -> None:
        super().__init__(
            f"I don't have a verified growth standard for {breed} yet, so I can't compare weight or feed to target.",
            "Ask me how the shed is doing instead.",
            f"{breed} కి ధృవీకరించిన పెరుగుదల ప్రమాణం నా దగ్గర ఇంకా లేదు, కాబట్టి బరువు లేదా ఫీడ్‌ను లక్ష్యంతో పోల్చలేను.",
            "బదులుగా షెడ్ ఎలా ఉందో అడగండి.",
        )
        self.breed = breed


class InsufficientData(DomainError):
    def __init__(self, what: str, what_te: str) -> None:
        super().__init__(
            f"I don't have enough recent records to work out {what}.",
            "Add today's readings for this shed, then ask me again.",
            f"{what_te} లెక్కించడానికి నా దగ్గర సరిపడా తాజా రికార్డులు లేవు.",
            "ఈ షెడ్ ఈరోజు రీడింగులు నమోదు చేసి, మళ్ళీ అడగండి.",
        )


class BeyondGrowthTable(InsufficientData):
    """A broiler plan would run past the last day of the cited growth table. Adding readings cannot help;
    a shorter plan can, when any days are left."""

    def __init__(self, label_en: str, label_te: str, breed: str, max_day: int, days_left: int) -> None:
        if days_left > 0:
            DomainError.__init__(
                self,
                f"I can plan only {days_left} more {'day' if days_left == 1 else 'days'} for {label_en}, "
                f"up to day {max_day} of the {breed} growth table.",
                f"Ask me for {days_left} {'day' if days_left == 1 else 'days'} or fewer.",
                f"{label_te} కి {breed} పెరుగుదల పట్టికలోని {max_day}వ రోజు వరకు, ఇంకా {days_left} రోజులకే ప్రణాళిక చేయగలను.",
                f"{days_left} రోజులు లేదా అంతకంటే తక్కువకు అడగండి.",
            )
        else:
            DomainError.__init__(
                self,
                f"{label_en} has reached the end of the {breed} growth table (day {max_day}), "
                "so I can't project its feed.",
                "Ask me how the shed is doing instead.",
                f"{label_te} {breed} పెరుగుదల పట్టిక చివరి రోజు ({max_day}) కి చేరింది, కాబట్టి ఫీడ్‌ను అంచనా వేయలేను.",
                "బదులుగా షెడ్ ఎలా ఉందో అడగండి.",
            )
        self.days_left = days_left
        self.values = {"max_day": max_day, "days_left": days_left}


class InvalidInput(DomainError):
    pass
