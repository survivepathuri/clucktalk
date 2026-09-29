"""``get_farm_profile`` and ``set_farm_mode``: contract or independent farm (docs/DESIGN.md §13.1).

``set_farm_mode`` is the first tool that changes something, so it follows the one confirmation pattern
(docs/DESIGN.md §5.1): propose -> read-back -> the farmer's "yes" -> the same tool again with ``proposal_id``.
Telugu: review status per string in docs/TELUGU_REVIEW.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from clucktalk.domain.errors import DomainError
from clucktalk.domain.profile import FarmMode, FarmProfile
from clucktalk.domain.proposals import PROPOSAL_TTL, Answer, Proposal, ProposalId, Reason
from clucktalk.i18n import Text
from clucktalk.server.confirm import ConfirmFlow
from clucktalk.server.errors import domain_error_result
from clucktalk.server.farm_state import DemoFarmSource
from clucktalk.server.tools import Capability, CapabilityRegistry

TOOL = "set_farm_mode"
ModeName = Literal["contract", "independent"]

PROFILE_TEXT = {
    FarmMode.CONTRACT: Text(
        "Your farm is set up as a contract farm: your company supplies the feed, so feed plans tell you how many "
        "bags to ask your supervisor for, without prices.",
        "మీ ఫారం కాంట్రాక్ట్ ఫారంగా సెట్ అయి ఉంది: ఫీడ్ మీ కంపెనీ ఇస్తుంది, కాబట్టి ఫీడ్ ప్లాన్ ధరలు లేకుండా, సూపర్‌వైజర్‌ని ఎన్ని బస్తాలు అడగాలో చెబుతుంది.",
    ),
    FarmMode.INDEPENDENT: Text(
        "Your farm is set up as an independent farm: you buy your own feed, so feed plans include a simulated price.",
        "మీ ఫారం సొంత ఫారంగా సెట్ అయి ఉంది: ఫీడ్ మీరే కొంటారు, కాబట్టి ఫీడ్ ప్లాన్‌లో అంచనా ధర (డెమో) కూడా ఉంటుంది.",
    ),
}
SWITCH_HINT = {  # keyed by the mode the farm could switch *to*
    FarmMode.CONTRACT: Text(
        "To change it, say: switch to contract farming.",
        "మార్చాలంటే 'switch to contract farming' అని చెప్పండి.",
    ),
    FarmMode.INDEPENDENT: Text(
        "To change it, say: switch to independent farming.",
        "మార్చాలంటే 'switch to independent farming' అని చెప్పండి.",
    ),
}
READ_BACK = {
    FarmMode.CONTRACT: Text(
        "Switch your farm to contract farming? Then I'll stop suggesting feed purchases and prices, and tell you "
        "how many bags to ask your supervisor for. Say yes to confirm, or no to keep it as it is.",
        "మీ ఫారంను కాంట్రాక్ట్ ఫారంగా మార్చాలా? అప్పుడు ఫీడ్ కొనుగోలు, ధరలు చెప్పను; సూపర్‌వైజర్‌ని ఎన్ని బస్తాలు "
        "అడగాలో చెబుతాను. మార్చాలంటే 'అవును', వద్దంటే 'వద్దు' అని చెప్పండి.",
    ),
    FarmMode.INDEPENDENT: Text(
        "Switch your farm to independent farming? Then I'll plan feed purchases with a simulated price. "
        "Say yes to confirm, or no to keep it as it is.",
        "మీ ఫారంను సొంత ఫారంగా మార్చాలా? అప్పుడు అంచనా ధర (డెమో)తో ఫీడ్ కొనుగోలు ప్లాన్ చెబుతాను. మార్చాలంటే 'అవును', వద్దంటే 'వద్దు' అని చెప్పండి.",
    ),
}
NOW = {
    FarmMode.CONTRACT: Text("Your farm is now set up as a contract farm.", "మీ ఫారం ఇప్పుడు కాంట్రాక్ట్ ఫారంగా సెట్ అయింది."),
    FarmMode.INDEPENDENT: Text("Your farm is now set up as an independent farm.", "మీ ఫారం ఇప్పుడు సొంత ఫారంగా సెట్ అయింది."),
}
ALREADY = {
    FarmMode.CONTRACT: Text(
        "Your farm is already set up as a contract farm, so nothing changed.",
        "మీ ఫారం ఇప్పటికే కాంట్రాక్ట్ ఫారంగా ఉంది, కాబట్టి ఏమీ మారలేదు.",
    ),
    FarmMode.INDEPENDENT: Text(
        "Your farm is already set up as an independent farm, so nothing changed.",
        "మీ ఫారం ఇప్పటికే సొంత ఫారంగా ఉంది, కాబట్టి ఏమీ మారలేదు.",
    ),
}
STAYS = {
    FarmMode.CONTRACT: Text("Your farm stays a contract farm.", "మీ ఫారం కాంట్రాక్ట్ ఫారంగానే ఉంటుంది."),
    FarmMode.INDEPENDENT: Text("Your farm stays an independent farm.", "మీ ఫారం సొంత ఫారంగానే ఉంటుంది."),
}
DONE = Text("Done.", "సరే.")
KEPT = Text("Okay, nothing changed.", "సరే, ఏమీ మారలేదు.")
CHANGED_SINCE = Text(
    "That change was made earlier and has been changed again since.",
    "ఆ మార్పు ఇంతకుముందే జరిగింది, తర్వాత మళ్ళీ మార్చబడింది.",
)
REASON_TEXT: dict[Reason, Text] = {
    "expired": Text("That request timed out, so nothing changed.", "ఆ అభ్యర్థన సమయం ముగిసింది, కాబట్టి ఏమీ మారలేదు."),
    "superseded": Text(
        "That request was replaced by a newer one, so nothing changed.",
        "ఆ అభ్యర్థన స్థానంలో కొత్తది వచ్చింది, కాబట్టి ఏమీ మారలేదు.",
    ),
    "changed": Text(
        "That's different from what I read back, so nothing changed yet.",
        "అది నేను చదివి వినిపించిన దానికి భిన్నంగా ఉంది, కాబట్టి ఇంకా ఏమీ మారలేదు.",
    ),
    "unknown": Text("I couldn't find that request, so nothing changed.", "ఆ అభ్యర్థన నాకు కనబడలేదు, కాబట్టి ఏమీ మారలేదు."),
    "cancelled_earlier": Text(
        "That request was already cancelled, so nothing changed.",
        "ఆ అభ్యర్థన ఇప్పటికే రద్దయింది, కాబట్టి ఏమీ మారలేదు.",
    ),
    "already_done": Text(
        "That change was already made earlier, so saying no now doesn't undo it.",
        "ఆ మార్పు ఇంతకుముందే జరిగిపోయింది, కాబట్టి ఇప్పుడు 'వద్దు' అన్నా అది వెనక్కి రాదు.",
    ),
}


def _join(*parts: Text) -> Text:
    return Text(" ".join(p.en for p in parts), " ".join(p.te for p in parts))


def _other(mode: FarmMode) -> FarmMode:
    return FarmMode.INDEPENDENT if mode is FarmMode.CONTRACT else FarmMode.CONTRACT


class FarmProfileOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_en: str
    text_te: str
    demo_data: bool
    mode: ModeName
    set_by: Literal["demo_default", "farmer"]
    updated_at: str | None  # ISO 8601 with offset; None until the farmer changes it
    has_contract_terms: bool  # contract mode only: whether set_contract_terms has been saved


class SetFarmModeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_en: str
    text_te: str
    demo_data: bool
    status: Literal["needs_confirmation", "changed", "already_set", "cancelled"]
    mode_requested: ModeName
    mode_now: ModeName
    proposal_id: str | None  # pass back with the farmer's answer (needs_confirmation only)
    expires_at: str | None
    expires_in_minutes: int | None
    reason: Literal["expired", "superseded", "changed", "unknown", "cancelled_earlier", "already_done"] | None
    replayed: bool  # true when this "yes" had already been applied: nothing changed this time


GET_DESCRIPTION = (
    "Use when the farmer asks what kind of farm this is set up as, contract (a company or integrator supplies "
    "chicks and feed) or independent (the farmer buys feed and sells birds), or why feed answers mention the "
    "supervisor or prices. Takes no input. Returns the farm's mode and what it changes."
)
SET_DESCRIPTION = (
    "Use when the farmer wants to change how the farm is run. `mode`: 'contract' (a company or integrator supplies "
    "chicks, feed and medicine; also 'company farming', 'agreement farming', 'integration') or 'independent' "
    "(the farmer buys feed and sells the birds; also 'own farm', 'apna farm', 'khud ka'). Always two calls: first "
    "only `mode`; nothing changes and the result reads the change back. Ask the farmer. Then call again with the "
    "same `mode`, the returned `proposal_id` and `answer`: 'yes' only for an explicit spoken yes (haan, avunu), "
    "'no' for no (nahi, vaddu)."
)
MODE_PARAM = Field(description="'contract' or 'independent'.")
PROPOSAL_PARAM = Field(
    default=None,
    description="Only on the second call: the proposal_id returned by the first call, sent with the answer.",
)
ANSWER_PARAM = Field(
    default=None,
    description="Only on the second call: 'yes' if the farmer said yes (haan, avunu), 'no' if they said no.",
)


def build_profile(source: DemoFarmSource) -> FarmProfileOutput:
    p = source.profile()
    has_terms = source.store.get_contract_terms(source.farm_id) is not None
    text = _join(PROFILE_TEXT[p.mode], SWITCH_HINT[_other(p.mode)])
    if p.mode is FarmMode.CONTRACT:
        note = (
            Text(
                "Your contract terms are saved, so plan_sale can show the growing charge.",
                "మీ కాంట్రాక్ట్ నిబంధనలు సేవ్ అయ్యాయి, కాబట్టి ప్లాన్ సేల్ గ్రోయింగ్ ఛార్జ్ చూపగలదు.",
            )
            if has_terms
            else Text(
                "Say your contract terms to see the growing charge in the sale plan.",
                "సేల్ ప్లాన్‌లో గ్రోయింగ్ ఛార్జ్ చూడాలంటే మీ కాంట్రాక్ట్ నిబంధనలు చెప్పండి.",
            )
        )
        text = _join(text, note)
    return FarmProfileOutput(
        text_en=text.en,
        text_te=text.te,
        demo_data=source.demo_data,
        mode=p.mode.value,
        set_by=p.set_by,
        updated_at=None if p.updated_at is None else p.updated_at.isoformat(),
        has_contract_terms=has_terms,
    )


def build_set_mode(
    source: DemoFarmSource, flow: ConfirmFlow, mode: FarmMode, proposal_id: str | None, answer: Answer | None
) -> SetFarmModeOutput:
    farm_id = source.farm_id
    fields: dict[str, Any] = {
        "demo_data": source.demo_data,
        "mode_requested": mode.value,
        "proposal_id": None,
        "expires_at": None,
        "expires_in_minutes": None,
        "reason": None,
        "replayed": False,
    }

    def apply(proposal: Proposal, now: datetime) -> dict[str, Any]:
        chosen = FarmMode(proposal.arguments["mode"])
        source.store.save_profile(FarmProfile(farm_id, chosen, "farmer", now))
        return {"mode": chosen.value}

    # Read inside the flow's transaction: never read back a "switch" to the mode the farm already has.
    result = flow.run(
        farm_id, TOOL, {"mode": mode.value}, proposal_id, answer, apply, in_place=lambda: source.profile().mode is mode
    )
    now_mode = source.profile().mode
    fields["reason"] = result.reason
    if result.status == "already_set":
        text = ALREADY[now_mode]
        return SetFarmModeOutput(
            text_en=text.en, text_te=text.te, status="already_set", mode_now=now_mode.value, **fields
        )
    if result.status == "needs_confirmation":
        p = result.proposal
        assert p is not None
        reason = [REASON_TEXT[result.reason]] if result.reason else []
        text = _join(*reason, READ_BACK[mode])
        fields.update(
            proposal_id=p.proposal_id,
            expires_at=p.expires_at.isoformat(),
            expires_in_minutes=int(PROPOSAL_TTL.total_seconds() // 60),
        )
        status: Literal["needs_confirmation", "changed", "cancelled"] = "needs_confirmation"
    elif result.status == "applied":
        assert result.proposal is not None and result.proposal.outcome is not None  # confirmed proposals carry one
        applied = FarmMode(result.proposal.outcome["mode"])
        fields["replayed"] = result.replayed
        text = _join(DONE, NOW[applied]) if applied is now_mode else _join(CHANGED_SINCE, NOW[now_mode])
        status = "changed"
    elif result.reason == "already_done":  # a "no" after the change was applied: say what holds, how to undo
        text = _join(REASON_TEXT["already_done"], NOW[now_mode], SWITCH_HINT[_other(now_mode)])
        status = "cancelled"
    else:
        text = _join(REASON_TEXT[result.reason], STAYS[now_mode]) if result.reason else _join(KEPT, STAYS[now_mode])
        status = "cancelled"
    return SetFarmModeOutput(text_en=text.en, text_te=text.te, status=status, mode_now=now_mode.value, **fields)


def _result(out: FarmProfileOutput | SetFarmModeOutput) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=out.text_en)], structured_content=out.model_dump(mode="json")
    )


def register(server: MCPServer, registry: CapabilityRegistry, source: DemoFarmSource) -> None:
    flow = ConfirmFlow(source.store, source.now)

    @server.tool(
        name="get_farm_profile",
        title="Farm type",
        description=GET_DESCRIPTION,
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False),
    )
    def get_farm_profile() -> Annotated[CallToolResult, FarmProfileOutput]:
        return _result(build_profile(source))

    @server.tool(
        name=TOOL,
        title="Change farm type",
        description=SET_DESCRIPTION,
        # Not read-only; idempotent: repeating the same yes never applies twice (docs/DESIGN.md §5.1).
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
        ),
    )
    def set_farm_mode(
        mode: Annotated[ModeName, MODE_PARAM],
        proposal_id: Annotated[ProposalId | None, PROPOSAL_PARAM] = None,
        answer: Annotated[Answer | None, ANSWER_PARAM] = None,
    ) -> Annotated[CallToolResult, SetFarmModeOutput]:
        try:
            out = build_set_mode(source, flow, FarmMode(mode), proposal_id, answer)
        except DomainError as err:
            return domain_error_result(err)
        return _result(out)

    registry.add(
        Capability(
            tool_name=TOOL,
            title=Text("Contract or independent farm", "కాంట్రాక్ట్ లేదా సొంత ఫారం"),
            example_en="Switch my farm to contract farming",  # help adds the closing punctuation
        )
    )
