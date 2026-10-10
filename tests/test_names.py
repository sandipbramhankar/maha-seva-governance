"""Maharashtra name structure and relationship inference."""
import pytest

from seva.engine.names import Relation, parse, relate, same_token


def test_three_part_name_is_split_as_given_patronymic_surname():
    p = parse("Prakash Dattatray Shinde")
    assert (p.given, p.patronymic, p.surname) == ("Prakash", "Dattatray", "Shinde")


def test_two_part_name_has_no_patronymic():
    p = parse("Meera Devi")
    assert p.given == "Meera" and p.surname == "Devi" and p.patronymic == ""


def test_honorifics_are_stripped():
    assert parse("Shri Prakash Dattatray Shinde").given == "Prakash"
    assert parse("Late Maruti Shinde").given == "Maruti"


def test_land_in_fathers_name_is_recognised_as_the_father():
    rel, why = relate("Dattatray Maruti Shinde", "Prakash Dattatray Shinde",
                      "Dattatray Shinde", "Maruti Shinde")
    assert rel is Relation.FATHER
    assert "father" in why.lower()


def test_fathers_record_confirms_the_grandfather():
    _, why = relate("Dattatray Maruti Shinde", "Prakash Dattatray Shinde",
                    "Dattatray Shinde", "Maruti Shinde")
    assert "three-generation chain" in why


def test_devanagari_record_resolves_to_the_applicant():
    rel, _ = relate("संदीप प्रभु "
                    "ब्राह्मणकर",
                    "Sandip Prabhu Bramhankar",
                    "Prabhu Bramhankar", "Vithoba Brahmankar")
    assert rel is Relation.SELF


def test_namesake_with_a_different_patronymic_is_not_the_applicant():
    rel, why = relate("Prakash Ganpat Shinde", "Prakash Dattatray Shinde",
                      "Dattatray Shinde", "Maruti Shinde")
    assert rel is Relation.FAMILY
    assert "namesake" in why


def test_different_surname_is_unrelated():
    rel, _ = relate("Vilas Govind Patil", "Prakash Dattatray Shinde",
                    "Dattatray Shinde", "Maruti Shinde")
    assert rel is Relation.UNRELATED


def test_spelling_variants_are_one_token():
    assert same_token("Bramhankar", "Brahmankar")
    assert same_token("Sandip", "Sandeep")
    assert not same_token("Prakash", "Dattatray")


def test_initial_matches_the_name_it_abbreviates():
    assert same_token("D", "Dattatray")
    assert not same_token("M", "Dattatray")
