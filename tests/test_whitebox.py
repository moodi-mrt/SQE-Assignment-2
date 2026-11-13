"""White-box tests for registration.py.

These were written after the black-box suite, by looking at the structure of
the code (see docs/cfg.png and the report). Each test states which path,
branch or condition it is aimed at. Expected results still come from the SRS,
so a test can fail when the code structure is reachable but wrong.

Node numbers (N1..N16) refer to the CFG of registration_decision() in
docs/cfg.png. Basis paths are P1..P8.
"""
import copy

import pytest

from registration import (
    Course,
    Student,
    check_credit_limit,
    prerequisites_satisfied,
    register_course,
    registration_decision,
    withdraw_course,
)


def student(**kw):
    base = dict(student_id="S100", completed_courses={"CS101"}, current_credits=9,
                outstanding_dues=0, registered_courses=set())
    base.update(kw)
    return Student(**base)


def course(**kw):
    base = dict(code="CS301", credit_hours=3, capacity=20, enrolled=5,
                prerequisites={"CS101"}, waitlist=[])
    base.update(kw)
    return Course(**base)


# ---------------------------------------------------------------------------
# B1 - basis path set for registration_decision()   V(G) = 8
# ---------------------------------------------------------------------------

def test_WB01_P1_negative_dues_raises():
    # N1 true -> N2
    with pytest.raises(ValueError, match="Invalid dues"):
        registration_decision(student(outstanding_dues=-1), course())


def test_WB02_P2_bad_enrollment_raises():
    # N1 false, N3 true -> N4
    with pytest.raises(ValueError, match="Invalid capacity or enrollment"):
        registration_decision(student(), course(enrolled=21))


def test_WB03_P3_large_dues_returns_dues_block():
    # N3 false, N5 true -> N6. Dues well above any threshold so this path is
    # reached whatever value the code compares against. Black-box tests never
    # got to line 51 (they used 1 and 500).
    assert registration_decision(student(outstanding_dues=1500), course()) == "DUES_BLOCK"


def test_WB04_P4_already_registered():
    # N5 false, N7 true -> N8
    s = student(registered_courses={"CS301"})
    assert registration_decision(s, course()) == "ALREADY_REGISTERED"


def test_WB05_P5_prerequisites_missing():
    # N7 false, N9 true -> N10
    assert registration_decision(student(completed_courses=set()), course()) == "PREREQUISITES_MISSING"


def test_WB06_P6_credit_limit():
    # N9 false, N11 true -> N12
    assert registration_decision(student(current_credits=18), course()) == "CREDIT_LIMIT"


def test_WB07_P7_full_course_waitlisted():
    # N11 false, N13 true -> N14.
    # In the original code N13 is "enrolled > capacity", which can never be
    # true because N3 already rejected that state, so P7 is infeasible there.
    # FR-08 says enrolled == capacity must give WAITLISTED.
    assert registration_decision(student(), course(enrolled=20)) == "WAITLISTED"


def test_WB08_P8_registered():
    # every decision false -> N15
    assert registration_decision(student(), course()) == "REGISTERED"


# ---------------------------------------------------------------------------
# B3 - MC/DC for N3:  not (0 <= enrolled <= capacity) or capacity < 1
#   A = 0 <= enrolled     B = enrolled <= capacity     C = capacity < 1
#   Python evaluates the chain left to right and stops early, so B is not
#   evaluated when A is False, and C is not evaluated when (A and B) is False.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "capacity, enrolled, raises",
    [
        pytest.param(20, 5, False, id="MC1-A_T-B_T-C_F"),
        pytest.param(20, -1, True, id="MC2-A_F-B_x-C_x"),   # pair MC1/MC2 -> A
        pytest.param(20, 21, True, id="MC3-A_T-B_F-C_x"),   # pair MC1/MC3 -> B
        pytest.param(0, 0, True, id="MC4-A_T-B_T-C_T"),     # pair MC1/MC4 -> C
    ],
)
def test_WB09_mcdc_capacity_enrollment_check(capacity, enrolled, raises):
    c = course(capacity=capacity, enrolled=enrolled)
    if raises:
        with pytest.raises(ValueError, match="Invalid capacity or enrollment"):
            registration_decision(student(), c)
    else:
        assert registration_decision(student(), c) == "REGISTERED"


def test_WB10_negative_capacity_short_circuits_before_C():
    # capacity = -3, enrolled = 0: A True, B False, so the left operand is
    # already True and C is never evaluated. Shows C can only decide the
    # outcome when capacity == enrolled == 0.
    with pytest.raises(ValueError, match="Invalid capacity or enrollment"):
        registration_decision(student(), course(capacity=-3, enrolled=0))


# ---------------------------------------------------------------------------
# B3 - MC/DC for register_course:
#   decision == "WAITLISTED" and student_id not in waitlist
#   D = decision == "WAITLISTED"      W = id not in waitlist
# ---------------------------------------------------------------------------

def test_WB11_mcdc_waitlist_D_true_W_true():
    # D T, W T -> append (pair with WB12 shows W, pair with WB13 shows D)
    c = course(enrolled=20)
    assert register_course(student(), c) == "WAITLISTED"
    assert c.waitlist == ["S100"]


def test_WB12_mcdc_waitlist_D_true_W_false():
    # D T, W F -> nothing appended
    c = course(enrolled=20, waitlist=["S100"])
    assert register_course(student(), c) == "WAITLISTED"
    assert c.waitlist == ["S100"]


def test_WB13_mcdc_waitlist_D_false_W_not_evaluated():
    # D F (CREDIT_LIMIT), W short-circuited -> nothing appended
    s = student(current_credits=17)
    c = course(enrolled=20)
    assert register_course(s, c) == "CREDIT_LIMIT"
    assert c.waitlist == []


def test_WB14_waitlist_keeps_other_students():
    # W True with a non-empty list, order must be kept
    c = course(enrolled=20, waitlist=["S007"])
    register_course(student(), c)
    assert c.waitlist == ["S007", "S100"]


# ---------------------------------------------------------------------------
# helpers: branch / condition targets
# ---------------------------------------------------------------------------

def test_WB15_prereq_empty_branch():
    # "if not required" true branch, completed set empty as well
    assert prerequisites_satisfied(set(), set()) is True


def test_WB16_prereq_superset_of_required():
    # non-empty branch, every required course is completed
    assert prerequisites_satisfied({"A", "B", "C"}, {"A", "C"}) is True


def test_WB17_prereq_one_of_two_missing():
    # non-empty branch, partial overlap must be False (all-of rule)
    assert prerequisites_satisfied({"A"}, {"A", "B"}) is False


@pytest.mark.parametrize(
    "current, new, expected",
    [
        pytest.param(14, 4, True, id="WB18-sum_18_max_course"),
        pytest.param(18, 1, False, id="WB19-sum_19"),
    ],
)
def test_credit_limit_return_expression(current, new, expected):
    # both outcomes of the final comparison in check_credit_limit
    assert check_credit_limit(current, new) is expected


def test_WB20_withdraw_true_branch_updates_enrolled():
    # withdraw_course: "not in registered" is False -> removal statements
    s = student(current_credits=12, registered_courses={"CS301"})
    c = course(enrolled=6)
    assert withdraw_course(s, c) is True
    assert s.current_credits == 9
    assert c.enrolled == 5


def test_WB21_withdraw_false_branch():
    s = student()
    c = course()
    before = (copy.deepcopy(s), copy.deepcopy(c))
    assert withdraw_course(s, c) is False
    assert (s, c) == before


def test_WB22_register_course_dues_path_no_side_effect():
    # register_course with a non REGISTERED/WAITLISTED decision: neither branch runs
    s = student(outstanding_dues=1500)
    c = course()
    assert register_course(s, c) == "DUES_BLOCK"
    assert s.registered_courses == set()
    assert c.enrolled == 5
