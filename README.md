# seva-governance

Ticket-based governance for Maharashtra citizen services.

Every citizen request receives a **Seva ID** at submission and keeps it through
every department that touches the file. Before an officer opens it, the request
is verified against the government's own repositories, and every decision —
automated or human — is sealed into a hash-linked audit chain.

Identity resolution across those repositories is performed by
[`indicer`](https://github.com/sandipbramhankar/indicer-hetero-match)
(Indian Patent Application 202621097866).

---

## The problem

A citizen applying for a caste certificate today must collect a verification
document from the Revenue Inspector in person. That errand is where money
changes hands: the officer is a gatekeeper the citizen cannot go around, and
nobody checks what he writes against the village register he is supposedly
reading from.

Two changes remove it.

**The citizen never collects a government document.** They supply only what
they already hold. Everything else is read directly from the department that
holds it — Aadhaar, the 7/12 land register, the ration database, PM-KISAN, LPG
subsidy records, vehicle registration, and this platform's own history.

**The officer's submission is checked against the record.** Contradictions are
on the screen before the file is opened, and approving past one requires a
written reason that stays in the audit chain under the officer's name.

A second problem is measurement. Existing trackers mark an application
"disposed" when the file closes, including when it is rejected or deemed
rejected, so a citizen can be counted as served while holding nothing. This
platform measures whether the certificate reached the citizen inside the
statutory period under the Maharashtra Right to Public Services Act, 2015.

---

## Running it

```bash
git clone https://github.com/sandipbramhankar/indicer-hetero-match.git ../indicer-hetero-match
pip install -e ../indicer-hetero-match
pip install -r requirements-dev.txt

python -m pytest -q                              # 68 tests
uvicorn seva.api.main:app --reload               # dashboard at http://127.0.0.1:8000
```

The dashboard is served at `/`, the JSON API under `/api/`.

### Deploying to Railway

`Procfile` and `railway.json` both start `uvicorn seva.api.main:app`, with
`/api/health` as the healthcheck. `runtime.txt` pins Python 3.11.

`requirements.txt` installs `indicer` from GitHub. This matters: both
`seva/engine/verification.py` and `seva/engine/fraud.py` import it at module
level, so a build without it fails at import rather than at request time.

---

## How a request is assessed

`seva/engine/orchestrator.py::assess` runs the whole stack:

```
run_checks          what each repository says about this applicant
FraudGraph.assess   who else is linked to them
score stack         GTS, ERS, CGS
run_consensus       how the specialised agents voted
AuditChain.append   hash-linked record of all of it
```

The verdict is a recommendation with reasons attached. A human still signs the
certificate. What changes is that they start from evidence rather than a blank
file, and whatever they decide is recorded against their name.

### Verdicts

| Verdict | Meaning |
|---|---|
| `APPROVE` | nothing contradicts the claim; the officer confirms rather than investigates |
| `INVESTIGATE` | a single source disagrees — a question, not yet a case |
| `ESCALATE` | several sources disagree, fraud risk is critical, or quorum failed |
| `REJECT` | the claim fails on the evidence |

Two guards override the composite score outright. **Quorum failure** — an
incomplete vote is never a decision, only a reason to involve a person. And a
**decisive-attribute failure** confirmed by several independent repositories:
a high average must never bury a specific red flag.

Whether income is decisive depends on the claim. An OBC claim is subject to the
creamy layer, so income decides; an SC claim is not, so it does not.

---

## Checks

`seva/engine/verification.py` compares seven attributes across seven sources.

| Attribute | Weight |
|---|---|
| Caste entry | 0.25 |
| Identity (name) | 0.18 |
| Lineage | 0.15 |
| Date of birth | 0.12 |
| Income evidence | 0.12 |
| Household link | 0.10 |
| Residence | 0.08 |

Two distinctions carry most of the weight of the design.

**A missing record is not a failed check.** An urban applicant with no land and
no ration card has nothing in those repositories. Scoring that against them
would invert the platform's purpose, so `NOT_AVAILABLE` is excluded from the
consistency score rather than counted as a mismatch.

**Land in the father's name is not an identity mismatch.** Agricultural land in
Maharashtra routinely stays in a father's or grandfather's name for a
generation after their death, because mutation is slow and costly. Reporting
that as a failed identity check would reject most genuine rural applicants;
reporting it as an identity match would assert that two people are one. It is
recorded as a household link, with the relationship named.

---

## Fraud graph

`seva/engine/fraud.py` scores an applicant's position in the graph of shared
identifiers rather than anything in their own file. No member of a ring looks
wrong alone.

Sharing a *village* is not evidence — in rural Maharashtra that would flag
everyone. Sharing a *premises* is. `_is_premises_address` draws that line, and
surnames are compared through indicer's phonetic encoding so that spelling and
script variants of one family name are not read as three different families.

---

## The RTS Act clock

| Flag | Condition |
|---|---|
| GREEN | comfortably within the statutory period |
| YELLOW | past the halfway mark |
| ORANGE | approaching the deadline |
| RED | the statutory limit has been breached |

A caste certificate allows 30 days across four desks, so roughly 7.5 days each.
`read_clock` names the desk currently holding the file and says when that desk
alone has overrun its share — the breach is locatable to one officer before the
overall deadline has passed.

---

## Seva ID

```
MH-THL-2026-GON-000001-4
│  │   │    │   │      └── Verhoeff check digit
│  │   │    │   └───────── sequence within district and year
│  │   │    └───────────── district code
│  │   └────────────────── year
│  └────────────────────── department code
└───────────────────────── state
```

Verhoeff rather than Luhn: it catches all single-digit errors *and* all
adjacent transpositions, which are the two mistakes people make reading a
number aloud at a counter. A mistyped ID fails validation instead of silently
resolving to another citizen's request.

---

## Demonstration data

Nine profiles in `seva/data/mock_sources.py`, each exercising a different
decision path. Every citizen is invented.

| Aadhaar | Expected | Why |
|---|---|---|
| 4821 | APPROVE | all seven sources agree |
| 9034 | APPROVE | Devanagari land record, Latin elsewhere, three spellings |
| 5567 | ESCALATE | claims SC-Mahar; 1952 village entry reads OBC-Kunbi |
| 7712 | ESCALATE | declares ₹85,000 against 6.4 ha, a 2023 SUV and withdrawn LPG subsidy |
| 3390 | INVESTIGATE | three-generation proof does not close |
| 1101–1103 | ESCALATE | one address, one mobile, three different surnames |
| 6648 | APPROVE | urban applicant, thin evidence, nothing contradicts it |

`seva/store.py` seeds these alongside bulk tickets across all 36 districts for
the dashboard.

---

## Layout

```
seva/
├── models.py              domain types, SLA table, service→department map
├── seva_id.py             issue, parse, Verhoeff check digit
├── store.py               ticket store and demo seeding
├── analytics.py           district, taluka, bottleneck and override rollups
├── data/
│   ├── maharashtra.py     36 districts across 6 divisions
│   ├── mock_sources.py    DataFabric over the seven repositories
│   └── officers.py        officer registry per stage and district
├── engine/
│   ├── names.py           Maharashtra name structure, relationship inference
│   ├── verification.py    the seven cross-source checks
│   ├── fraud.py           shared-identifier graph
│   ├── consensus.py       agent voting and quorum
│   ├── scoring.py         GTS, ERS, CGS and the guards
│   ├── audit.py           hash-linked chain
│   └── orchestrator.py    assess() — runs the whole stack
├── workflow/
│   ├── stages.py          stage chains, officers, open/close
│   └── sla.py             RTS Act clock
└── api/main.py            FastAPI app and static dashboard

web/                       dashboard (vanilla JS, no build step)
tests/                     68 tests
```

---

## Not built yet

- **Persistence.** Everything is in memory; the store reseeds on restart.
- **Real source adapters.** All seven read `DataFabric`.
- **Authentication.** No officer login; the override path is modelled but not
  gated.

---

## Status

Prototype, built to demonstrate the approach. Not deployed against any live
government system, and every citizen in the demonstration data is invented.
