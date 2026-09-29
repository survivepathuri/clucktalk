"""``set_contract_terms``: save the farmer's own contract growing-charge terms (docs/DESIGN.md §13.3).

Follows the one confirmation pattern (docs/DESIGN.md §5.1), same as set_farm_mode. The terms are never a named
company's rates (CLAUDE.md safety rule): they are numbers the farmer reads out from their own agreement. Once
saved, plan_sale uses them to show how an extra day changes the growing charge (evidence for contract farmers).
Telugu: review status per string in docs/TELUGU_REVIEW.md.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from clucktalk.domain.errors import DomainError
from clucktalk.domain.profile import FCR_POINT, ContractTerms
from clucktalk.domain.proposals import PROPOSAL_TTL, Answer, Proposal, ProposalId, Reason
from clucktalk.i18n import Text
from clucktalk.server.confirm import ConfirmFlow
from clucktalk.server.errors import domain_error_result
from clucktalk.server.farm_state import DemoFarmSource
from clucktalk.server.render import rupees
from clucktalk.server.tools import Capability, CapabilityRegistry

TOOL = "set_contract_terms"

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
        "Those terms were already saved earlier, so saying no now doesn't undo it.",
        "ఆ నిబంధనలు ఇంతకుముందే సేవ్ అయ్యాయి, కాబట్టి ఇప్పుడు 'వద్దు' అన్నా అది వెనక్కి రాదు.",
    ),
}
KEPT = Text("Okay, nothing changed.", "సరే, ఏమీ మారలేదు.")


def _join(*parts: Text) -> Text:
    return Text(" ".join(p.en for p in parts), " ".join(p.te for p in parts))


class ContractTermsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_rate_per_kg_inr: float
    standard_fcr: float
    mortality_allowance_pct: float
    incentive_per_kg_per_fcr_point_inr: float
    deduction_per_kg_per_fcr_point_inr: float
    updated_at: str | None  # None for "proposed" (not yet saved)


class SetContractTermsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_en: str
    text_te: str
    demo_data: bool
    status: str  # needs_confirmation | changed | cancelled
    terms: ContractTermsOut | None  # currently saved, after this call
    proposed: ContractTermsOut  # the numbers in this call, so a needs_confirmation read-back is cross-modal
    fcr_point: float  # the "per how much FCR" unit the read-back speaks (docs/DESIGN.md §13.3)
    proposal_id: str | None
    expires_at: str | None
    expires_in_minutes: int | None
    reason: str | None
    replayed: bool


DESCRIPTION = (
    "Use when a contract farmer wants to save or update their own growing-charge terms, so plan_sale can show "
    "how an extra day changes the growing charge. Give all five numbers from the farmer's own agreement: "
    "`base_rate_per_kg` (rupees per kg live weight at the standard FCR), `standard_fcr`, `mortality_allowance_pct` "
    "(cumulative mortality with no deduction), `incentive_per_kg_per_fcr_point` and `deduction_per_kg_per_fcr_point` "
    "(rupees per kg, per 0.1 FCR better/worse than standard; 0 if unknown). Never suggest numbers from any company: "
    "ask the farmer to read them from their own paperwork. Always two calls: first only the five numbers; nothing "
    "changes and the result reads them back. Then call again with the same numbers plus the returned `proposal_id` "
    "and `answer`: 'yes' for an explicit spoken yes (haan, avunu), 'no' for no (nahi, vaddu)."
)
RATE_PARAM = Field(gt=0, description="Rupees per kg live weight at the standard FCR.")
FCR_PARAM = Field(gt=0, description="The contract's standard (target) FCR.")
ALLOW_PARAM = Field(ge=0, le=100, description="Cumulative mortality percent with no deduction.")
INCENTIVE_PARAM = Field(ge=0, description="Rupees per kg, per 0.1 FCR better than standard. 0 if none.")
DEDUCTION_PARAM = Field(ge=0, description="Rupees per kg, per 0.1 FCR worse than standard. 0 if none.")
PROPOSAL_PARAM = Field(default=None, description="Only on the second call: the proposal_id from the first call.")
ANSWER_PARAM = Field(default=None, description="Only on the second call: 'yes' if the farmer said yes, 'no' if no.")


def _read_back(base: Decimal, fcr: Decimal, allow: Decimal, inc: Decimal, ded: Decimal) -> Text:
    return Text(
        f"Save your contract terms: {rupees(base)} per kg at FCR {fcr}, mortality allowance {allow}%, "
        f"{rupees(inc)} more per kg for every 0.1 better FCR, {rupees(ded)} less per kg for every 0.1 worse FCR. "
        "Say yes to confirm, or no to keep it as it is.",
        f"మీ కాంట్రాక్ట్ నిబంధనలు సేవ్ చేయాలా: FCR {fcr} వద్ద కిలోకు {rupees(base)}, మరణాల మినహాయింపు {allow}%, "
        f"ప్రతి 0.1 మెరుగైన FCRకి కిలోకు {rupees(inc)} ఎక్కువ, ప్రతి 0.1 తక్కువ FCRకి కిలోకు {rupees(ded)} తక్కువ. "
        "సేవ్ చేయాలంటే 'అవును', వద్దంటే 'వద్దు' అని చెప్పండి.",
    )


def build_set_terms(
    source: DemoFarmSource,
    flow: ConfirmFlow,
    base_rate_per_kg: Decimal,
    standard_fcr: Decimal,
    mortality_allowance_pct: Decimal,
    incentive_per_kg_per_fcr_point: Decimal,
    deduction_per_kg_per_fcr_point: Decimal,
    proposal_id: str | None,
    answer: Answer | None,
) -> SetContractTermsOutput:
    farm_id = source.farm_id
    args: dict[str, Any] = {
        "base_rate_per_kg": str(base_rate_per_kg),
        "standard_fcr": str(standard_fcr),
        "mortality_allowance_pct": str(mortality_allowance_pct),
        "incentive_per_kg_per_fcr_point": str(incentive_per_kg_per_fcr_point),
        "deduction_per_kg_per_fcr_point": str(deduction_per_kg_per_fcr_point),
    }

    def apply(proposal: Proposal, now: datetime) -> dict[str, Any]:
        terms = ContractTerms(
            farm_id=farm_id,
            base_rate_per_kg=Decimal(proposal.arguments["base_rate_per_kg"]),
            standard_fcr=Decimal(proposal.arguments["standard_fcr"]),
            mortality_allowance_pct=Decimal(proposal.arguments["mortality_allowance_pct"]),
            incentive_per_kg_per_fcr_point=Decimal(proposal.arguments["incentive_per_kg_per_fcr_point"]),
            deduction_per_kg_per_fcr_point=Decimal(proposal.arguments["deduction_per_kg_per_fcr_point"]),
            updated_at=now,
        )
        source.store.save_contract_terms(terms)
        return args

    def current_matches() -> bool:
        existing = source.store.get_contract_terms(farm_id)
        return (
            existing is not None
            and {
                "base_rate_per_kg": str(existing.base_rate_per_kg),
                "standard_fcr": str(existing.standard_fcr),
                "mortality_allowance_pct": str(existing.mortality_allowance_pct),
                "incentive_per_kg_per_fcr_point": str(existing.incentive_per_kg_per_fcr_point),
                "deduction_per_kg_per_fcr_point": str(existing.deduction_per_kg_per_fcr_point),
            }
            == args
        )

    result = flow.run(farm_id, TOOL, args, proposal_id, answer, apply, in_place=current_matches)
    saved = source.store.get_contract_terms(farm_id)
    out_terms = (
        ContractTermsOut(
            base_rate_per_kg_inr=float(saved.base_rate_per_kg),
            standard_fcr=float(saved.standard_fcr),
            mortality_allowance_pct=float(saved.mortality_allowance_pct),
            incentive_per_kg_per_fcr_point_inr=float(saved.incentive_per_kg_per_fcr_point),
            deduction_per_kg_per_fcr_point_inr=float(saved.deduction_per_kg_per_fcr_point),
            updated_at=saved.updated_at.isoformat(),
        )
        if saved is not None
        else None
    )
    # Always present (even once applied), so every number the read-back speaks is also in structuredContent.
    proposed = ContractTermsOut(
        base_rate_per_kg_inr=float(base_rate_per_kg),
        standard_fcr=float(standard_fcr),
        mortality_allowance_pct=float(mortality_allowance_pct),
        incentive_per_kg_per_fcr_point_inr=float(incentive_per_kg_per_fcr_point),
        deduction_per_kg_per_fcr_point_inr=float(deduction_per_kg_per_fcr_point),
        updated_at=None,
    )
    fields: dict[str, Any] = {
        "demo_data": source.demo_data,
        "terms": out_terms,
        "proposed": proposed,
        "fcr_point": float(FCR_POINT),
        "proposal_id": None,
        "expires_at": None,
        "expires_in_minutes": None,
        "reason": result.reason,
        "replayed": False,
    }
    if result.status == "already_set":
        text = Text(
            "Those are already your saved contract terms, so nothing changed.",
            "ఇవి ఇప్పటికే మీ సేవ్ చేసిన కాంట్రాక్ట్ నిబంధనలు, కాబట్టి ఏమీ మారలేదు.",
        )
        return SetContractTermsOutput(text_en=text.en, text_te=text.te, status="already_set", **fields)
    if result.status == "needs_confirmation":
        p = result.proposal
        assert p is not None
        reason = [REASON_TEXT[result.reason]] if result.reason else []
        read_back = _read_back(
            base_rate_per_kg,
            standard_fcr,
            mortality_allowance_pct,
            incentive_per_kg_per_fcr_point,
            deduction_per_kg_per_fcr_point,
        )
        text = _join(*reason, read_back)
        fields.update(
            proposal_id=p.proposal_id,
            expires_at=p.expires_at.isoformat(),
            expires_in_minutes=int(PROPOSAL_TTL.total_seconds() // 60),
        )
        return SetContractTermsOutput(text_en=text.en, text_te=text.te, status="needs_confirmation", **fields)
    if result.status == "applied":
        fields["replayed"] = result.replayed
        text = Text("Done. Your contract terms are saved.", "సరే. మీ కాంట్రాక్ట్ నిబంధనలు సేవ్ అయ్యాయి.")
        return SetContractTermsOutput(text_en=text.en, text_te=text.te, status="changed", **fields)
    if result.reason == "already_done":
        text = REASON_TEXT["already_done"]
    else:
        text = _join(REASON_TEXT[result.reason], KEPT) if result.reason else KEPT
    return SetContractTermsOutput(text_en=text.en, text_te=text.te, status="cancelled", **fields)


def register(server: MCPServer, registry: CapabilityRegistry, source: DemoFarmSource) -> None:
    flow = ConfirmFlow(source.store, source.now)

    @server.tool(
        name=TOOL,
        title="Save contract terms",
        description=DESCRIPTION,
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
        ),
    )
    def set_contract_terms(
        base_rate_per_kg: Annotated[float, RATE_PARAM],
        standard_fcr: Annotated[float, FCR_PARAM],
        mortality_allowance_pct: Annotated[float, ALLOW_PARAM],
        incentive_per_kg_per_fcr_point: Annotated[float, INCENTIVE_PARAM],
        deduction_per_kg_per_fcr_point: Annotated[float, DEDUCTION_PARAM],
        proposal_id: Annotated[ProposalId | None, PROPOSAL_PARAM] = None,
        answer: Annotated[Answer | None, ANSWER_PARAM] = None,
    ) -> Annotated[CallToolResult, SetContractTermsOutput]:
        try:
            out = build_set_terms(
                source,
                flow,
                Decimal(str(base_rate_per_kg)),
                Decimal(str(standard_fcr)),
                Decimal(str(mortality_allowance_pct)),
                Decimal(str(incentive_per_kg_per_fcr_point)),
                Decimal(str(deduction_per_kg_per_fcr_point)),
                proposal_id,
                answer,
            )
        except DomainError as err:
            return domain_error_result(err)
        return CallToolResult(
            content=[TextContent(type="text", text=out.text_en)], structured_content=out.model_dump(mode="json")
        )

    registry.add(
        Capability(
            tool_name=TOOL,
            title=Text("Save your contract terms", "మీ కాంట్రాక్ట్ నిబంధనలు సేవ్ చేయండి"),
            example_en="Save my contract terms",
        )
    )
