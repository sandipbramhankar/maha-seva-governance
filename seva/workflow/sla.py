"""
Right to Services clock
========================
The Maharashtra Right to Public Services Act, 2015 gives every notified service
a deadline. The Act has been in force for a decade and is widely ignored,
because nothing makes a breach visible while it is happening. A deadline nobody
can see is not a deadline.

This module turns the statutory period into a running clock on every ticket and
on every stage within it, so a delay is visible on the day it starts rather
than in an annual report.

A ticket carries two clocks:

  the statutory clock   the whole request against its notified period
  the stage clock       the current desk against its share of that period

The second is what makes an officer accountable. A file that spent 26 of 30
days on one desk and 4 days moving through four others has one problem, and the
dashboard should name it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from seva.models import Flag, SevaTicket, Stage

#: Fractions of the statutory period consumed before each flag is raised.
YELLOW_AT = 0.50
ORANGE_AT = 0.80
RED_AT    = 1.00

#: A stage holding a file beyond this multiple of its own allowance is named
#: as the bottleneck even when the ticket as a whole is still within time.
STAGE_OVERRUN_MULTIPLE = 1.5


@dataclass
class ClockReading:
    age_days:        float
    sla_days:        int
    consumed:        float            # fraction of the statutory period used
    days_remaining:  float
    flag:            Flag
    breached:        bool
    stage_days:      float
    stage_allowance: float
    stage_overrun:   bool
    reason:          str

    def as_dict(self) -> Dict[str, object]:
        return {
            "age_days":        round(self.age_days, 2),
            "sla_days":        self.sla_days,
            "consumed":        round(self.consumed, 4),
            "days_remaining":  round(self.days_remaining, 2),
            "flag":            self.flag.value,
            "breached":        self.breached,
            "stage_days":      round(self.stage_days, 2),
            "stage_allowance": round(self.stage_allowance, 2),
            "stage_overrun":   self.stage_overrun,
            "reason":          self.reason,
        }


def stage_allowance(ticket: SevaTicket, stages: List[Stage]) -> float:
    """
    Days allotted to one desk: the statutory period divided across the stages
    that actually require a human. Automated steps take no share because they
    complete in seconds.
    """
    human_stages = [s for s in stages
                    if s not in (Stage.SUBMITTED, Stage.AUTO_VERIFICATION,
                                 Stage.ISSUED, Stage.REJECTED)]
    return ticket.sla_days / max(len(human_stages), 1)


def read_clock(ticket: SevaTicket, stages: List[Stage],
               now: Optional[datetime] = None) -> ClockReading:
    """Current state of both clocks, with the reason in plain words."""
    now = now or datetime.now(timezone.utc)
    age = ticket.age_days(now)
    sla = ticket.sla_days
    consumed = age / sla if sla else 0.0
    remaining = sla - age

    # time on the current desk
    stage_days = 0.0
    for event in reversed(ticket.history):
        if event.is_open:
            entered = datetime.fromisoformat(event.entered_at)
            stage_days = (now - entered).total_seconds() / 86400.0
            break

    allowance = stage_allowance(ticket, stages)
    overrun = (not ticket.is_closed) and stage_days > allowance * STAGE_OVERRUN_MULTIPLE

    if ticket.is_closed:
        breached = age > sla
        flag = Flag.RED if breached else Flag.GREEN
        reason = (f"Closed after {age:.0f} days against a {sla}-day period."
                  if not breached else
                  f"Closed after {age:.0f} days, {age - sla:.0f} days beyond "
                  f"the {sla}-day statutory period.")
        return ClockReading(age, sla, consumed, remaining, flag, breached,
                            stage_days, allowance, False, reason)

    breached = consumed >= RED_AT
    if breached:
        flag = Flag.RED
        reason = (f"Statutory period breached: {age:.0f} days against a "
                  f"{sla}-day limit, still at {ticket.current_stage.value}.")
    elif consumed >= ORANGE_AT:
        flag = Flag.ORANGE
        reason = (f"{remaining:.0f} days left of {sla}, still at "
                  f"{ticket.current_stage.value}.")
    elif consumed >= YELLOW_AT:
        flag = Flag.YELLOW
        reason = f"Half the {sla}-day period used, at {ticket.current_stage.value}."
    else:
        flag = Flag.GREEN
        reason = f"Within time: {remaining:.0f} of {sla} days remaining."

    if overrun and flag is Flag.GREEN:
        flag = Flag.YELLOW
    if overrun:
        reason += (f" This desk has held it {stage_days:.0f} days against an "
                   f"allowance of {allowance:.0f}.")

    return ClockReading(age, sla, consumed, remaining, flag, breached,
                        stage_days, allowance, overrun, reason)
