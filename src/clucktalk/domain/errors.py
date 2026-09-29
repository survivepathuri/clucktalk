"""Domain errors. Each carries a customer-safe message and one next step, in English and Telugu; the tool layer
turns it into the structured MCP error (docs/DESIGN.md §5, rule 4). No codes, IDs, or JSON in the message.
Telugu: review status per string in docs/TELUGU_REVIEW.md."""

from __future__ import annotations

from datetime import date


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


class NotSoldByWeight(DomainError):
    """Sale-day planning compares a live weight against a market price; layers are not sold that way."""

    def __init__(self, label_en: str, label_te: str) -> None:
        super().__init__(
            f"{label_en} is a layer flock, so sell-day planning by live weight doesn't apply to it.",
            "Ask me about its egg production or feed instead.",
            f"{label_te} గుడ్ల మంద, కాబట్టి బరువు ఆధారంగా అమ్మకం రోజు ప్రణాళిక దీనికి వర్తించదు.",
            "బదులుగా గుడ్ల ఉత్పత్తి లేదా ఫీడ్ గురించి అడగండి.",
        )


class AnswerWithoutProposal(DomainError):
    """A yes/no arrived without the request it answers (docs/DESIGN.md §5.1)."""

    def __init__(self) -> None:
        super().__init__(
            "There's nothing waiting for your yes or no right now, so nothing changed.",
            "Tell me again what you'd like to change.",
            "ఇప్పుడు మీ 'అవును' లేదా 'వద్దు' కోసం ఏదీ ఎదురుచూడటం లేదు, కాబట్టి ఏమీ మారలేదు.",
            "మీరు ఏమి మార్చాలనుకుంటున్నారో మళ్ళీ చెప్పండి.",
        )


class DeathsExceedLiveBirds(DomainError):
    """More deaths than birds alive at the start of that day (docs/DESIGN.md §13.4); the bound uses the
    house's own history, seed and previously logged days together, once the record book overlay is wired."""

    def __init__(self, label_en: str, label_te: str, deaths: int, live_before: int) -> None:
        super().__init__(
            f"{label_en} only had {live_before} birds alive before that day, so {deaths} deaths can't be right.",
            "Check the number and try again.",
            f"ఆ రోజుకు ముందు {label_te}లో {live_before} కోళ్లు మాత్రమే బతికి ఉన్నాయి, కాబట్టి {deaths} మరణాలు సరైనవి కావు.",
            "సంఖ్యను సరిచూసి మళ్ళీ చెప్పండి.",
        )
        self.values = {"deaths": deaths, "live_before": live_before}


class NothingToRecord(DomainError):
    """log_daily_record was called with every field empty (docs/DESIGN.md §13.4)."""

    def __init__(self, label_en: str, label_te: str) -> None:
        super().__init__(
            f"I didn't catch anything to record for {label_en}.",
            "Tell me deaths, feed bags, a weight sample, or a medicine or vaccine given.",
            f"{label_te} కోసం రికార్డ్ చేయడానికి ఏమీ అందలేదు.",
            "మరణాలు, ఫీడ్ బస్తాలు, బరువు నమూనా, లేదా ఇచ్చిన మందు లేదా వ్యాక్సిన్ చెప్పండి.",
        )


class WeightSampleNeedsBirdCount(DomainError):
    """An average weight without how many birds were weighed can't be stored (docs/DESIGN.md §13.4)."""

    def __init__(self, label_en: str, label_te: str) -> None:
        super().__init__(
            f"I have an average weight for {label_en} but not how many birds were weighed.",
            "Tell me how many birds you weighed to get that average.",
            f"{label_te} సగటు బరువు నాకు వచ్చింది, కానీ ఎన్ని కోళ్లను తూచారో తెలియలేదు.",
            "ఆ సగటు కోసం ఎన్ని కోళ్లను తూచారో చెప్పండి.",
        )


class RecordDayOutOfRange(DomainError):
    """A record day must be on or after the house's placement day, and never in the future."""

    def __init__(self, label_en: str, label_te: str, day: date, as_of: date) -> None:
        if day > as_of:
            super().__init__(
                f"I can't log a record for {label_en} in the future.",
                "Tell me about today or an earlier day.",
                f"{label_te} కి భవిష్యత్తు రోజుకు రికార్డ్ నమోదు చేయలేను.",
                "ఈరోజు లేదా అంతకుముందు రోజు గురించి చెప్పండి.",
            )
        else:
            super().__init__(
                f"{label_en} wasn't placed yet on that day, so I can't log a record for it.",
                "Tell me about a day on or after the house started.",
                f"ఆ రోజుకి {label_te} ఇంకా వేయలేదు, కాబట్టి రికార్డ్ నమోదు చేయలేను.",
                "ఇంటి ప్రారంభమైన రోజు లేదా తర్వాతి రోజు గురించి చెప్పండి.",
            )
        self.day = day


class MissingAnswer(DomainError):
    """A request ID arrived without the farmer's yes or no (docs/DESIGN.md §5.1)."""

    def __init__(self) -> None:
        super().__init__(
            "I didn't catch whether that was a yes or a no, so nothing changed.",
            "Please say yes or no.",
            "అది 'అవును'నా 'వద్దు'నా అని నాకు అర్థం కాలేదు, కాబట్టి ఏమీ మారలేదు.",
            "దయచేసి 'అవును' లేదా 'వద్దు' అని చెప్పండి.",
        )
