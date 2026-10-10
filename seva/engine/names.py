"""
Maharashtra name structure
===========================
A Maharashtra personal name is three parts:

    Prakash   Dattatray   Shinde
    given     father's    surname
              given name

The middle part is a patronymic, not a middle name. That convention carries
information no fuzzy string match can recover, and it is the key to reading
village records correctly.

Consider a 7/12 extract naming "Dattatray Maruti Shinde" against an applicant
"Prakash Dattatray Shinde". Compared as whole strings the two share two tokens
out of three and score around 0.75, which is high enough to look like a match
and low enough to look like a discrepancy: the worst possible answer. Read
structurally, the record says something exact. The applicant's patronymic is
this record-holder's given name, and the surnames agree, so the land stands in
the applicant's father's name, which in rural Maharashtra is the ordinary case
rather than a problem.

The same reading validates the next generation up. If the record's own
patronymic is Maruti, and the applicant states a grandfather called Maruti
Shinde, the three-generation chain closes on the record itself rather than on
a document the applicant was sent to collect.

Token comparison is phonetic, through indicer, so Dattatray, Dattatraya and
दत्तात्रय are one name.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from indicer.pipeline.stage1_script import normalise_script
from indicer.pipeline.stage2_structural import structural_normalise
from indicer.pipeline.stage3_phonetic import code_string

#: Titles and suffixes that appear on records but are not part of the name.
HONORIFICS = {
    "shri", "shree", "sri", "smt", "smti", "kum", "km", "dr", "prof",
    "late", "shrimati", "mr", "mrs", "ms", "adv", "er",
}


class Relation(str, Enum):
    SELF        = "self"
    FATHER      = "father"
    GRANDFATHER = "grandfather"
    FAMILY      = "family"       # surname agrees, position does not
    UNRELATED   = "unrelated"
    UNKNOWN     = "unknown"      # not enough of a name to judge


RELATION_LABEL = {
    Relation.SELF:        "the applicant",
    Relation.FATHER:      "the applicant's father",
    Relation.GRANDFATHER: "the applicant's grandfather",
    Relation.FAMILY:      "someone of the same surname",
    Relation.UNRELATED:   "nobody in this household",
    Relation.UNKNOWN:     "an unreadable name",
}


@dataclass
class NameParts:
    raw:        str
    given:      str = ""
    patronymic: str = ""
    surname:    str = ""
    tokens:     Optional[List[str]] = None

    @property
    def is_usable(self) -> bool:
        return bool(self.given and self.surname)


def _phonetic(token: str) -> str:
    """
    Phonetic code for one token, via indicer.

    This is what makes Bramhankar, Brahmankar and ब्राह्मणकर compare equal.
    """
    if not token:
        return ""
    romanised, _ = normalise_script(token)
    components = structural_normalise(romanised)
    if not components:
        return ""
    return code_string(components[0])


def is_initial(token: str) -> bool:
    return len(token.strip().strip(".")) == 1


def same_token(a: str, b: str) -> bool:
    """True when two name tokens are the same name, allowing for spelling."""
    if not a or not b:
        return False
    if a.strip().lower() == b.strip().lower():
        return True
    ca, cb = _phonetic(a), _phonetic(b)
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    # An initial stands for the name it abbreviates: "Dattatray" and "D".
    # This is a weak match by construction, since one letter is shared by many
    # names, so callers that report it must say so rather than claim proof.
    if is_initial(a) or is_initial(b):
        return ca[:1] == cb[:1]
    return False


def parse(full_name: str) -> NameParts:
    """
    Split a name into given, patronymic and surname.

    Two tokens are read as given plus surname, which is how urban and
    abbreviated records usually appear. Four or more tokens keep the first as
    given, the last as surname, and the second as the patronymic.
    """
    raw = (full_name or "").strip()
    cleaned = raw.replace(".", " ").replace(",", " ")
    tokens = [t for t in cleaned.split()
              if t and t.strip().lower().strip(".") not in HONORIFICS]
    if not tokens:
        return NameParts(raw=raw, tokens=[])
    if len(tokens) == 1:
        return NameParts(raw=raw, given=tokens[0], tokens=tokens)
    if len(tokens) == 2:
        return NameParts(raw=raw, given=tokens[0], surname=tokens[1], tokens=tokens)
    return NameParts(raw=raw, given=tokens[0], patronymic=tokens[1],
                     surname=tokens[-1], tokens=tokens)


def relate(record_name: str,
           applicant: str,
           father: Optional[str] = None,
           grandfather: Optional[str] = None) -> tuple[Relation, str]:
    """
    Work out whose name is on a record, and say why.

    Returns the relation and a sentence an officer can read.
    """
    rec = parse(record_name)
    app = parse(applicant)

    if not rec.is_usable or not app.is_usable:
        return Relation.UNKNOWN, (
            f"{record_name!r} could not be read as a name in the "
            f"given / father's name / surname form."
        )

    if not same_token(rec.surname, app.surname):
        return Relation.UNRELATED, (
            f"The surname on the record ({rec.surname}) is not "
            f"{app.surname}."
        )

    # The applicant themselves.
    if same_token(rec.given, app.given):
        if app.patronymic and rec.patronymic and \
                not same_token(rec.patronymic, app.patronymic):
            return Relation.FAMILY, (
                f"Same given name and surname, but the record's patronymic "
                f"({rec.patronymic}) is not {app.patronymic}. This is a "
                f"namesake in the same village, not the applicant."
            )
        return Relation.SELF, "The record stands in the applicant's own name."

    # The father: the applicant's patronymic is this person's given name.
    father_given = parse(father).given if father else ""
    if app.patronymic and same_token(rec.given, app.patronymic):
        extra = ""
        if grandfather:
            gf_given = parse(grandfather).given
            if rec.patronymic and gf_given and same_token(rec.patronymic, gf_given):
                if is_initial(rec.patronymic) or is_initial(gf_given):
                    extra = (f" The record abbreviates the father's own "
                             f"patronymic to {rec.patronymic}, which is "
                             f"consistent with the stated grandfather "
                             f"{gf_given} but does not on its own prove the "
                             f"third generation.")
                else:
                    extra = (f" The record's own patronymic is {rec.patronymic}, "
                             f"which matches the stated grandfather and closes "
                             f"the three-generation chain.")
            elif rec.patronymic and gf_given:
                extra = (f" The record names {rec.patronymic} as the father's "
                         f"father, not the stated grandfather {gf_given}.")
        return Relation.FATHER, (
            f"The record stands in the father's name: the applicant's "
            f"patronymic ({app.patronymic}) is this holder's given name.{extra}"
        )
    if father_given and same_token(rec.given, father_given):
        return Relation.FATHER, "The record stands in the stated father's name."

    # The grandfather.
    gf_given = parse(grandfather).given if grandfather else ""
    if gf_given and same_token(rec.given, gf_given):
        return Relation.GRANDFATHER, (
            "The record stands in the stated grandfather's name, which is "
            "usual for land that has not been mutated since."
        )

    return Relation.FAMILY, (
        f"Surname matches but {rec.given} is neither the applicant, the stated "
        f"father nor the stated grandfather."
    )


def lineage_consistent(record_name: str, applicant: str,
                       grandfather: Optional[str]) -> Optional[bool]:
    """
    Whether a father's record independently confirms the grandfather.

    Returns None when the record carries no patronymic to test.
    """
    rec = parse(record_name)
    if not rec.patronymic or not grandfather:
        return None
    return same_token(rec.patronymic, parse(grandfather).given)


if __name__ == "__main__":
    cases = [
        ("Dattatray Maruti Shinde", "Prakash Dattatray Shinde",
         "Dattatray Shinde", "Maruti Shinde"),
        ("Dattatray M Shinde", "Prakash Dattatray Shinde",
         "Dattatray Shinde", "Maruti Shinde"),
        ("संदीप प्रभु ब्राह्मणकर", "Sandip Prabhu Bramhankar",
         "Prabhu Bramhankar", "Vithoba Brahmankar"),
        ("Ramesh Tukaram Meshram", "Ramesh Tukaram Meshram",
         "Tukaram Nagorao Meshram", "Nagorao Meshram"),
        ("Baburao Madavi", "Sunil Baburao Madavi",
         "Baburao Madavi", "Lakshman Madavi"),
        ("Vilas Govind Patil", "Prakash Dattatray Shinde",
         "Dattatray Shinde", "Maruti Shinde"),
        ("Prakash Ganpat Shinde", "Prakash Dattatray Shinde",
         "Dattatray Shinde", "Maruti Shinde"),
    ]
    for rec, app, fa, gf in cases:
        rel, why = relate(rec, app, fa, gf)
        print(f"{rec:28s} -> {rel.value:12s} {why}")
