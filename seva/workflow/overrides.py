"""
Officer action and the override record
=======================================
An officer may always overrule the engine. That is deliberate: the engine reads
repositories, and repositories are wrong often enough that a system which could
not be overruled would be worse than the one it replaces. A Talathi who knows
the family, or has seen a document the databases never captured, must be able
to pass a file the machine flagged.

What the officer may not do is overrule it silently.

Before a flagged file moves on, this module requires three things:

    the officer holds the file      only the open desk can act on it
    each flag is named              a blanket approval is not an answer
    a reason is given per flag      recorded, attributed, and counted

The reason is checked for substance only lightly, and that limit is worth
stating plainly: no validator can tell a considered justification from a
plausible-sounding one. The deterrent is not the check. It is that the text is
attributed, permanent, and counted — an officer who waves through forty flags
appears on the integrity view whatever they typed, and `analytics.officer_
overrides` is what surfaces them.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Sequence

from seva.engine.scoring import decisive_attributes
from seva.models import MatchStatus, SevaTicket, Stage, Verdict
from seva.workflow.stages import Officer, advance, reject


class OverrideRefused(Exception):
    """
    The action cannot proceed as submitted.

    Carries `field` so the interface can mark the control that needs
    attention, rather than showing one message over the whole form.
    """

    def __init__(self, message: str, field: str = "action") -> None:
        super().__init__(message)
        self.message = message
        self.field = field


# ---------------------------------------------------------------------------
# What the officer has to address
# ---------------------------------------------------------------------------

@dataclass
class OpenFlag:
    """One thing the engine raised that has not been answered."""
    key: str            # stable identifier the client sends back
    label: str          # what to show the officer
    detail: str         # why the engine raised it
    severity: str       # "decisive" | "advisory"
    sources: List[str]  # repositories that disagreed

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


#: Actions that move a file forward. These are the ones that require every
#: decisive flag to be answered first.
FORWARD_ACTIONS = {"forward", "approve"}

#: Actions that stop a file. A reason is required, but flags need not be
#: answered: refusing a flagged application is the engine's own recommendation.
STOP_ACTIONS = {"reject", "return"}

ALL_ACTIONS = FORWARD_ACTIONS | STOP_ACTIONS

#: Minimum length for a reason. Short enough not to obstruct a busy desk, long
#: enough that "ok" does not pass. See the module docstring on what this does
#: and does not achieve.
MIN_REASON_CHARS = 20

#: Reasons that say nothing, however long. Matched case-insensitively against
#: the whole stripped text, so a reason that merely contains one of these
#: alongside real content still passes.
EMPTY_REASONS = {
    "ok", "okay", "fine", "done", "approved", "verified", "checked",
    "as per rules", "as per norms", "no objection", "correct", "genuine",
    "satisfied", "recommended", "forwarded", "all documents verified",
    "verified and found correct", "found correct",
}

#: Fraud risk at or above which the graph itself becomes a flag to answer.
FRAUD_FLAG_AT = 50.0


def open_flags(ticket: SevaTicket) -> List[OpenFlag]:
    """
    Everything the engine raised on this ticket that an officer must address.

    Returns an empty list for a clean application, which is the common case and
    the one that should cost an officer no extra keystrokes.
    """
    report = ticket.verification
    if report is None:
        return []

    decisive = set(decisive_attributes(ticket.service,
                                       ticket.citizen.claimed_caste))

    # Group mismatches by attribute: several repositories contradicting one
    # claim is one thing to answer, not four.
    grouped: Dict[str, Dict[str, object]] = {}
    for check in report.checks:
        if check.status is not MatchStatus.MISMATCH:
            continue
        entry = grouped.setdefault(
            check.attribute, {"sources": [], "notes": []}
        )
        entry["sources"].append(check.source)        # type: ignore[union-attr]
        if check.note:
            entry["notes"].append(check.note)        # type: ignore[union-attr]

    flags: List[OpenFlag] = []
    for attribute, entry in grouped.items():
        sources: List[str] = entry["sources"]        # type: ignore[assignment]
        notes: List[str] = entry["notes"]            # type: ignore[assignment]
        count = len(sources)
        detail = notes[0] if notes else "Contradicted by the record."
        if count > 1:
            detail = (
                f"{count} repositories disagree with this claim. {detail}"
            )
        flags.append(OpenFlag(
            key=f"check:{attribute}",
            label=attribute,
            detail=detail,
            severity="decisive" if attribute in decisive else "advisory",
            sources=sources,
        ))

    fraud = getattr(report, "fraud", None)
    if fraud is not None and getattr(fraud, "frs", 0.0) >= FRAUD_FLAG_AT:
        findings = [f for f in getattr(fraud, "findings", [])
                    if not f.startswith("No shared identifiers")]
        flags.append(OpenFlag(
            key="fraud:graph",
            label="Linked applications",
            detail=(findings[0] if findings
                    else f"Fraud risk {fraud.frs:.0f} out of 100."),
            severity="decisive",
            sources=["Fraud graph"],
        ))

    # Decisive first: those are the ones that block.
    flags.sort(key=lambda f: (f.severity != "decisive", f.label))
    return flags


def decisive_keys(flags: Sequence[OpenFlag]) -> List[str]:
    return [f.key for f in flags if f.severity == "decisive"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _reason_is_substantive(reason: str) -> bool:
    text = " ".join((reason or "").split())
    if len(text) < MIN_REASON_CHARS:
        return False
    return text.strip().strip(".").lower() not in EMPTY_REASONS


def validate_action(
    ticket: SevaTicket,
    officer: Officer,
    action: str,
    remark: str,
    overrode: Sequence[str],
) -> List[OpenFlag]:
    """
    Check that this officer may take this action on this ticket.

    Raises OverrideRefused with the offending field named. Returns the flags
    that were answered, so the caller can record them.
    """
    action = (action or "").strip().lower()
    if action not in ALL_ACTIONS:
        raise OverrideRefused(
            f"{action!r} is not an action. Use one of: "
            f"{', '.join(sorted(ALL_ACTIONS))}.",
            field="action",
        )

    if ticket.is_closed:
        raise OverrideRefused(
            f"{ticket.seva_id} was already closed as {ticket.outcome}. "
            f"A closed file cannot be acted on again.",
            field="action",
        )

    held_by = _open_event(ticket)
    if held_by is None:
        raise OverrideRefused(
            f"{ticket.seva_id} is not on any desk right now, so there is "
            f"nothing to act on.",
            field="action",
        )
    if held_by.officer_id != officer.officer_id:
        raise OverrideRefused(
            f"{ticket.seva_id} is on {held_by.officer_name}'s desk "
            f"({held_by.officer_id}). Only the officer holding a file can "
            f"act on it.",
            field="officer_id",
        )

    flags = open_flags(ticket)
    answered = [f for f in flags if f.key in set(overrode)]

    if action in STOP_ACTIONS:
        # Stopping a file needs a reason the citizen can be shown and can
        # appeal against, but does not require answering the engine's flags.
        if not _reason_is_substantive(remark):
            raise OverrideRefused(
                f"Refusing or returning a file needs a reason of at least "
                f"{MIN_REASON_CHARS} characters that the citizen can be "
                f"shown and can appeal against.",
                field="remark",
            )
        return answered

    # -- forwarding or approving -------------------------------------------
    required = set(decisive_keys(flags))
    unanswered = required - set(overrode)
    if unanswered:
        missing = sorted(f.label for f in flags if f.key in unanswered)
        raise OverrideRefused(
            f"The record contradicts this application on: "
            f"{', '.join(missing)}. To move it forward anyway, name each one "
            f"and say why the record is wrong or does not apply.",
            field="overrode",
        )

    unknown = set(overrode) - {f.key for f in flags}
    if unknown:
        raise OverrideRefused(
            f"These were not raised on this file: {', '.join(sorted(unknown))}.",
            field="overrode",
        )

    if answered and not _reason_is_substantive(remark):
        raise OverrideRefused(
            f"Overriding {len(answered)} flag(s) needs a reason of at least "
            f"{MIN_REASON_CHARS} characters. It is recorded against your name "
            f"and counted on the integrity view.",
            field="remark",
        )

    return answered


def _open_event(ticket: SevaTicket):
    for event in reversed(ticket.history):
        if event.is_open:
            return event
    return None


# ---------------------------------------------------------------------------
# Performing the action
# ---------------------------------------------------------------------------

@dataclass
class ActionResult:
    seva_id: str
    action: str
    from_stage: str
    to_stage: str
    overrode: List[str]
    audit_hash: Optional[str]
    closed: bool

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


def perform(
    ticket: SevaTicket,
    officer: Officer,
    action: str,
    remark: str = "",
    overrode: Optional[Sequence[str]] = None,
    chain=None,
    at: Optional[str] = None,
) -> ActionResult:
    """
    Validate and carry out an officer's decision, sealing it into the chain.

    The audit entry is written whatever the action, including a plain forward
    with nothing overridden: a file's history should show who held it and for
    how long, not only the moments something went wrong.
    """
    overrode = list(overrode or [])
    answered = validate_action(ticket, officer, action, remark, overrode)

    action = action.strip().lower()
    from_stage = ticket.current_stage
    labels = [f.label for f in answered]

    if action in STOP_ACTIONS:
        reject(ticket, officer, reason=remark, at=at)
        # `reject` closes the desk without the override list, so record it.
        for event in reversed(ticket.history):
            if event.exited_at and event.action == "rejected":
                event.overrode_flags = labels
                break
    else:
        advance(ticket, officer, remark=remark, overrode=labels, at=at)

    audit_hash = None
    if chain is not None:
        entry = chain.append(
            event=f"officer_{action}",
            actor_id=officer.officer_id,
            actor_name=officer.name,
            payload={
                "role": officer.role,
                "from_stage": from_stage.value,
                "to_stage": ticket.current_stage.value,
                "remark": remark,
                "overrode": labels,
                "flags_open_at_decision": [f.label for f in open_flags(ticket)],
            },
        )
        audit_hash = entry.entry_hash

    return ActionResult(
        seva_id=ticket.seva_id,
        action=action,
        from_stage=from_stage.value,
        to_stage=ticket.current_stage.value,
        overrode=labels,
        audit_hash=audit_hash,
        closed=ticket.is_closed,
    )
