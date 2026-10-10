"""
Aggregation
============
Turns a pile of tickets into the four questions a Chief Minister's review asks:

  Where is it stuck?      district and taluka pendency, ranked by breach rate
  Which desk is slow?     stage-level dwell time across the state
  Who is overriding?      officers waving through flags the engine raised
  Is it getting better?   filings against closures, week by week

One rule runs through all of it: a raw pending count is never the headline. A
district with eleven million people will always top a raw count and that tells
nobody anything. Breach rate and load per officer are what separate a busy
district from a failing one.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

from seva.models import Department, Flag, Stage
from seva.data.maharashtra import DISTRICT_BY_NAME, DISTRICTS
from seva.store import TicketStore, TicketView
from seva.workflow.stages import STAGE_ROLE


def _rate(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


def summary(views: List[TicketView]) -> Dict[str, object]:
    """Statewide headline figures."""
    open_v = [v for v in views if not v.ticket.is_closed]
    closed = [v for v in views if v.ticket.is_closed]
    breached = [v for v in open_v if v.breached]
    red = [v for v in open_v if v.flag is Flag.RED]
    on_time = [v for v in closed if not v.breached]

    ages = [v.age_days for v in open_v]
    return {
        "total":          len(views),
        "open":           len(open_v),
        "closed":         len(closed),
        "breached":       len(breached),
        "breach_rate":    _rate(len(breached), len(open_v)),
        "red":            len(red),
        "orange":         sum(1 for v in open_v if v.flag is Flag.ORANGE),
        "yellow":         sum(1 for v in open_v if v.flag is Flag.YELLOW),
        "green":          sum(1 for v in open_v if v.flag is Flag.GREEN),
        "on_time_rate":   _rate(len(on_time), len(closed)),
        "avg_open_age":   round(sum(ages) / len(ages), 1) if ages else 0.0,
        "oldest_open":    round(max(ages), 1) if ages else 0.0,
        "engine_verified": sum(1 for v in views if v.engine_verified),
    }


def by_district(views: List[TicketView],
                department: Optional[str] = None) -> List[Dict[str, object]]:
    """One row per district, ordered by breach rate then by volume."""
    buckets: Dict[str, List[TicketView]] = defaultdict(list)
    for v in views:
        if department and v.ticket.department.value != department:
            continue
        buckets[v.ticket.district].append(v)

    rows: List[Dict[str, object]] = []
    for district in DISTRICTS:
        group = buckets.get(district.name, [])
        open_v = [v for v in group if not v.ticket.is_closed]
        breached = [v for v in open_v if v.breached]
        ages = [v.age_days for v in open_v]

        worst_stage, worst_days = "", 0.0
        stage_days: Dict[str, List[float]] = defaultdict(list)
        for v in open_v:
            stage_days[v.ticket.current_stage.value].append(v.stage_days)
        for stage, days in stage_days.items():
            avg = sum(days) / len(days)
            if avg > worst_days:
                worst_stage, worst_days = stage, avg

        rows.append({
            "district":    district.name,
            "code":        district.code,
            "division":    district.division,
            "talukas":     len(district.talukas),
            "total":       len(group),
            "open":        len(open_v),
            "breached":    len(breached),
            "breach_rate": _rate(len(breached), len(open_v)),
            "red":         sum(1 for v in open_v if v.flag is Flag.RED),
            "orange":      sum(1 for v in open_v if v.flag is Flag.ORANGE),
            "yellow":      sum(1 for v in open_v if v.flag is Flag.YELLOW),
            "green":       sum(1 for v in open_v if v.flag is Flag.GREEN),
            "avg_age":     round(sum(ages) / len(ages), 1) if ages else 0.0,
            "worst_stage": worst_stage,
            "worst_stage_days": round(worst_days, 1),
        })
    rows.sort(key=lambda r: (-r["breach_rate"], -r["open"]))
    return rows


def by_taluka(views: List[TicketView], district: str,
              department: Optional[str] = None) -> List[Dict[str, object]]:
    """Drill-down inside one district."""
    d = DISTRICT_BY_NAME.get(district)
    if d is None:
        return []
    buckets: Dict[str, List[TicketView]] = defaultdict(list)
    for v in views:
        if v.ticket.district != district:
            continue
        if department and v.ticket.department.value != department:
            continue
        buckets[v.ticket.taluka].append(v)

    rows: List[Dict[str, object]] = []
    for taluka in d.talukas:
        group = buckets.get(taluka, [])
        open_v = [v for v in group if not v.ticket.is_closed]
        breached = [v for v in open_v if v.breached]
        ages = [v.age_days for v in open_v]
        rows.append({
            "taluka":      taluka,
            "district":    district,
            "total":       len(group),
            "open":        len(open_v),
            "breached":    len(breached),
            "breach_rate": _rate(len(breached), len(open_v)),
            "red":         sum(1 for v in open_v if v.flag is Flag.RED),
            "orange":      sum(1 for v in open_v if v.flag is Flag.ORANGE),
            "yellow":      sum(1 for v in open_v if v.flag is Flag.YELLOW),
            "green":       sum(1 for v in open_v if v.flag is Flag.GREEN),
            "avg_age":     round(sum(ages) / len(ages), 1) if ages else 0.0,
        })
    rows.sort(key=lambda r: (-r["breach_rate"], -r["open"]))
    return rows


def by_department(views: List[TicketView]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for dept in Department:
        group = [v for v in views if v.ticket.department is dept]
        open_v = [v for v in group if not v.ticket.is_closed]
        breached = [v for v in open_v if v.breached]
        closed = [v for v in group if v.ticket.is_closed]
        ages = [v.age_days for v in open_v]
        services = Counter(v.ticket.service.value for v in group)
        rows.append({
            "department":  dept.value,
            "total":       len(group),
            "open":        len(open_v),
            "closed":      len(closed),
            "breached":    len(breached),
            "breach_rate": _rate(len(breached), len(open_v)),
            "red":         sum(1 for v in open_v if v.flag is Flag.RED),
            "orange":      sum(1 for v in open_v if v.flag is Flag.ORANGE),
            "yellow":      sum(1 for v in open_v if v.flag is Flag.YELLOW),
            "green":       sum(1 for v in open_v if v.flag is Flag.GREEN),
            "avg_age":     round(sum(ages) / len(ages), 1) if ages else 0.0,
            "top_service": services.most_common(1)[0][0] if services else "",
        })
    rows.sort(key=lambda r: -r["open"])
    return rows


def bottlenecks(views: List[TicketView]) -> List[Dict[str, object]]:
    """
    Which desk holds files longest, statewide.

    This is the answer to the question nobody can currently answer: of the
    thirty days a caste certificate takes, where do they go?
    """
    held: Dict[str, List[float]] = defaultdict(list)
    for v in views:
        if v.ticket.is_closed:
            continue
        held[v.ticket.current_stage.value].append(v.stage_days)

    rows = []
    for stage, days in held.items():
        rows.append({
            "stage":    stage,
            "role":     next((STAGE_ROLE[s] for s in Stage
                              if s.value == stage), ""),
            "pending":  len(days),
            "avg_days": round(sum(days) / len(days), 1),
            "max_days": round(max(days), 1),
        })
    rows.sort(key=lambda r: -r["avg_days"])
    return rows


def override_watch(store: TicketStore, views: List[TicketView],
                   min_overrides: int = 2) -> List[Dict[str, object]]:
    """
    Officers who closed a stage while waving a raised flag through.

    An override is legitimate. An officer who overrides on most of their files
    is a pattern, and a pattern is what an inspection should start from. This
    list is a prompt to look, never a finding.
    """
    handled: Counter = Counter()
    overrode: Counter = Counter()
    names: Dict[str, str] = {}
    places: Dict[str, str] = {}

    for ticket in store.all():
        for ev in ticket.history:
            if ev.officer_id in ("SYSTEM", ""):
                continue
            if ev.is_open:
                continue
            handled[ev.officer_id] += 1
            names[ev.officer_id] = ev.officer_name
            places[ev.officer_id] = f"{ticket.taluka}, {ticket.district}"
            if ev.overrode_flags:
                overrode[ev.officer_id] += 1

    rows = []
    for officer_id, count in overrode.items():
        if count < min_overrides:
            continue
        total = handled[officer_id]
        rows.append({
            "officer_id":    officer_id,
            "officer":       names.get(officer_id, ""),
            "posting":       places.get(officer_id, ""),
            "files_closed":  total,
            "overrides":     count,
            "override_rate": _rate(count, total),
        })
    rows.sort(key=lambda r: (-r["override_rate"], -r["overrides"]))
    return rows


def red_flag_queue(views: List[TicketView], limit: int = 40,
                   department: Optional[str] = None,
                   district: Optional[str] = None) -> List[Dict[str, object]]:
    """Open tickets most overdue, worst first."""
    rows = [v for v in views
            if not v.ticket.is_closed and v.flag in (Flag.RED, Flag.ORANGE)]
    if department:
        rows = [v for v in rows if v.ticket.department.value == department]
    if district:
        rows = [v for v in rows if v.ticket.district == district]
    rows.sort(key=lambda v: -(v.age_days - v.ticket.sla_days))
    return [v.as_dict() for v in rows[:limit]]


def weekly_trend(views: List[TicketView], weeks: int = 12,
                 now: Optional[datetime] = None) -> List[Dict[str, object]]:
    """Filings against closures, oldest week first."""
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(weeks=weeks)
    filed: Counter = Counter()
    closed: Counter = Counter()

    for v in views:
        t = v.ticket
        sub = datetime.fromisoformat(t.submitted_at)
        if sub >= start:
            filed[((sub - start).days // 7)] += 1
        if t.closed_at:
            cl = datetime.fromisoformat(t.closed_at)
            if cl >= start:
                closed[((cl - start).days // 7)] += 1

    out = []
    for w in range(weeks):
        label = (start + timedelta(weeks=w)).strftime("%d %b")
        out.append({"week": label, "filed": filed.get(w, 0),
                    "closed": closed.get(w, 0)})
    return out
