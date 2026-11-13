"""Black-box tests for the Student Course Registration System.

All expected values here come from REQUIREMENTS.md (FR-01 .. FR-15), not from
reading registration.py. Test design sheets are in docs/blackbox_test_design.xlsx
and docs/decision_table.xlsx.

Test ID prefixes
    ECP-xx  equivalence class partitioning
    BVA-xx  boundary value analysis
    DT-xx   decision table rules (registration_decision)
    ST-xx   state change checks for register / withdraw

Suite optimisation (A5): where two techniques produced exactly the same call
with the same inputs and the same expected result, the case is only executed
once and the pytest id lists every technique ID it covers, e.g.
"ECP-07|BVA-19|DT-06". Cases that only share an expected output but use
different inputs are kept separate.
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


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def make_student(**overrides):
    """Baseline eligible student: no dues, 12 credits, has passed CS101."""
    data = dict(
        student_id="S001",
        completed_courses={"CS101"},
        current_credits=12,
        outstanding_dues=0,
        registered_courses=set(),
    )
    data.update(overrides)
    return Student(**data)


def make_course(**overrides):
    """Baseline open course: 3 credit hours, 10/30 seats taken, needs CS101."""
    data = dict(
        code="CS201",
        credit_hours=3,
        capacity=30,
        enrolled=10,
        prerequisites={"CS101"},
        waitlist=[],
    )
    data.update(overrides)
    return Course(**data)


def snapshot(student, course):
    return copy.deepcopy(student), copy.deepcopy(course)


# ---------------------------------------------------------------------------
# FR-01 / FR-02  check_credit_limit
# ---------------------------------------------------------------------------

CREDIT_LIMIT_CASES = [
    # (current, new, expected)
    pytest.param(12, 3, True, id="ECP-01"),          # valid total well under 18
    pytest.param(17, 4, False, id="ECP-02"),         # valid inputs, total over 18
    pytest.param(0, 3, True, id="BVA-01"),           # current credits min
    pytest.param(18, 1, False, id="BVA-02"),         # current credits max
    pytest.param(10, 1, True, id="BVA-05"),          # course credits min
    pytest.param(10, 4, True, id="BVA-06"),          # course credits max
    pytest.param(14, 3, True, id="BVA-09"),          # total 17 (just below)
    pytest.param(15, 3, True, id="BVA-10"),          # total 18 (on boundary) - SRS scenario 1
    pytest.param(16, 3, False, id="BVA-11"),         # total 19 (just above) - SRS scenario 2
]


@pytest.mark.parametrize("current, new, expected", CREDIT_LIMIT_CASES)
def test_check_credit_limit(current, new, expected):
    assert check_credit_limit(current, new) is expected


CREDIT_ERROR_CASES = [
    pytest.param(20, 3, "Invalid current credits", id="ECP-03"),
    pytest.param(-2, 3, "Invalid current credits", id="ECP-04"),
    pytest.param(10, 6, "Invalid course credits", id="ECP-05"),
    pytest.param(10, 0, "Invalid course credits", id="ECP-06|BVA-07"),
    pytest.param(-1, 3, "Invalid current credits", id="BVA-03"),
    pytest.param(19, 3, "Invalid current credits", id="BVA-04"),
    pytest.param(10, 5, "Invalid course credits", id="BVA-08"),
    # FR-02: current credits are validated before course credits
    pytest.param(25, 9, "Invalid current credits", id="ECP-17"),
]


@pytest.mark.parametrize("current, new, message", CREDIT_ERROR_CASES)
def test_check_credit_limit_rejects_invalid_values(current, new, message):
    with pytest.raises(ValueError, match=message):
        check_credit_limit(current, new)


# ---------------------------------------------------------------------------
# FR-03  prerequisites_satisfied
# ---------------------------------------------------------------------------

PREREQ_CASES = [
    pytest.param({"CS101"}, set(), True, id="ECP-10"),                       # no prerequisites
    pytest.param({"CS101", "MATH101", "ENG101"}, {"CS101", "MATH101"}, True, id="ECP-11"),  # all done
    pytest.param({"CS101"}, {"CS101", "MATH101"}, False, id="ECP-12"),       # only some done (SRS scenario 3)
    pytest.param({"ENG101"}, {"CS101", "MATH101"}, False, id="ECP-13"),      # none done
]


@pytest.mark.parametrize("completed, required, expected", PREREQ_CASES)
def test_prerequisites_satisfied(completed, required, expected):
    assert prerequisites_satisfied(completed, required) is expected


# ---------------------------------------------------------------------------
# FR-04 .. FR-09  registration_decision outcomes
# ---------------------------------------------------------------------------

DECISION_CASES = [
    # (student overrides, course overrides, expected status)

    # baseline eligible student + open course. Exact same input was designed
    # independently in ECP (dues = 0, seats available), BVA (dues = 0) and
    # the decision table (all conditions false).
    pytest.param({}, {}, "REGISTERED", id="ECP-07|ECP-14|BVA-19|DT-06"),

    # dues
    pytest.param({"outstanding_dues": 500}, {}, "DUES_BLOCK", id="ECP-08|DT-01"),
    pytest.param({"outstanding_dues": 1}, {}, "DUES_BLOCK", id="BVA-20"),  # SRS scenario 4

    # already registered
    pytest.param({"registered_courses": {"CS201"}}, {}, "ALREADY_REGISTERED", id="ECP-16|DT-02"),

    # prerequisites
    pytest.param({"completed_courses": set()}, {}, "PREREQUISITES_MISSING", id="DT-03"),
    pytest.param({"completed_courses": {"CS101"}},
                 {"prerequisites": {"CS101", "MATH101"}},
                 "PREREQUISITES_MISSING", id="ECP-18"),

    # credit limit through the full decision
    pytest.param({"current_credits": 16}, {}, "CREDIT_LIMIT", id="DT-04"),
    pytest.param({"current_credits": 15}, {}, "REGISTERED", id="BVA-22"),

    # availability
    pytest.param({}, {"enrolled": 30}, "WAITLISTED", id="ECP-15|BVA-13|DT-05"),  # SRS scenario 5
    pytest.param({}, {"enrolled": 29}, "REGISTERED", id="BVA-12"),
    pytest.param({}, {"enrolled": 0}, "REGISTERED", id="BVA-15"),
    pytest.param({}, {"capacity": 1, "enrolled": 0}, "REGISTERED", id="BVA-17"),
    pytest.param({}, {"capacity": 1, "enrolled": 1}, "WAITLISTED", id="BVA-23"),

    # FR-09 priority combinations (more than one condition applies)
    pytest.param({"outstanding_dues": 200, "registered_courses": {"CS201"},
                  "completed_courses": set(), "current_credits": 18},
                 {"enrolled": 30}, "DUES_BLOCK", id="DT-07"),
    pytest.param({"registered_courses": {"CS201"}, "completed_courses": set(),
                  "current_credits": 18},
                 {"enrolled": 30}, "ALREADY_REGISTERED", id="DT-08"),
    pytest.param({"completed_courses": set(), "current_credits": 18},
                 {"enrolled": 30}, "PREREQUISITES_MISSING", id="DT-09"),
    pytest.param({"current_credits": 17}, {"enrolled": 30}, "CREDIT_LIMIT", id="DT-10"),
]


@pytest.mark.parametrize("s_over, c_over, expected", DECISION_CASES)
def test_registration_decision(s_over, c_over, expected):
    student = make_student(**s_over)
    course = make_course(**c_over)
    assert registration_decision(student, course) == expected


DECISION_ERROR_CASES = [
    pytest.param({"outstanding_dues": -50}, {}, "Invalid dues", id="ECP-09"),
    pytest.param({"outstanding_dues": -1}, {}, "Invalid dues", id="BVA-21"),
    pytest.param({}, {"enrolled": 31}, "Invalid capacity or enrollment", id="BVA-14"),
    pytest.param({}, {"enrolled": -1}, "Invalid capacity or enrollment", id="BVA-16"),
    pytest.param({}, {"capacity": 0, "enrolled": 0}, "Invalid capacity or enrollment", id="BVA-18"),
    # FR-15: dues are validated before capacity/enrollment
    pytest.param({"outstanding_dues": -5}, {"capacity": 0, "enrolled": 3}, "Invalid dues", id="ECP-19"),
]


@pytest.mark.parametrize("s_over, c_over, message", DECISION_ERROR_CASES)
def test_registration_decision_rejects_invalid_data(s_over, c_over, message):
    with pytest.raises(ValueError, match=message):
        registration_decision(make_student(**s_over), make_course(**c_over))


def test_ST10_decision_does_not_mutate_objects():
    # FR-10
    student = make_student()
    course = make_course(enrolled=30)
    before = snapshot(student, course)
    registration_decision(student, course)
    assert (student, course) == before


# ---------------------------------------------------------------------------
# FR-11 / FR-12  register_course state changes
# ---------------------------------------------------------------------------

def test_ST01_register_success_updates_state():
    student = make_student()
    course = make_course()
    assert register_course(student, course) == "REGISTERED"
    assert "CS201" in student.registered_courses
    assert student.current_credits == 15
    assert course.enrolled == 11
    assert course.waitlist == []


def test_ST02_register_full_course_only_adds_to_waitlist():
    student = make_student()
    course = make_course(enrolled=30)
    assert register_course(student, course) == "WAITLISTED"
    assert course.waitlist == ["S001"]
    assert student.registered_courses == set()
    assert student.current_credits == 12
    assert course.enrolled == 30


def test_ST03_waitlist_does_not_store_duplicates():
    student = make_student()
    course = make_course(enrolled=30, waitlist=["S001"])
    assert register_course(student, course) == "WAITLISTED"
    assert course.waitlist == ["S001"]


def test_ST11_register_up_to_exactly_18_credits():
    # combined-credit boundary with state check (SRS scenario 1)
    student = make_student(current_credits=15)
    course = make_course()
    assert register_course(student, course) == "REGISTERED"
    assert student.current_credits == 18


@pytest.mark.parametrize(
    "s_over, c_over, expected",
    [
        pytest.param({"outstanding_dues": 1}, {}, "DUES_BLOCK", id="ST-04"),
        pytest.param({"current_credits": 16}, {}, "CREDIT_LIMIT", id="ST-05"),
        pytest.param({"completed_courses": set()}, {}, "PREREQUISITES_MISSING", id="ST-06"),
        pytest.param({"registered_courses": {"CS201"}, "current_credits": 15}, {},
                     "ALREADY_REGISTERED", id="ST-07"),
    ],
)
def test_failed_registration_leaves_state_unchanged(s_over, c_over, expected):
    student = make_student(**s_over)
    course = make_course(**c_over)
    before = snapshot(student, course)
    assert register_course(student, course) == expected
    assert (student, course) == before


def test_ST12_invalid_data_raises_and_leaves_state_unchanged():
    student = make_student(outstanding_dues=-10)
    course = make_course()
    before = snapshot(student, course)
    with pytest.raises(ValueError, match="Invalid dues"):
        register_course(student, course)
    assert (student, course) == before


# ---------------------------------------------------------------------------
# FR-13 / FR-14  withdraw_course
# ---------------------------------------------------------------------------

def test_ST08_withdraw_enrolled_student():
    # SRS scenario 6
    student = make_student(current_credits=15, registered_courses={"CS201"})
    course = make_course(enrolled=11)
    assert withdraw_course(student, course) is True
    assert "CS201" not in student.registered_courses
    assert student.current_credits == 12
    assert course.enrolled == 10


def test_ST13_register_then_withdraw_restores_original_state():
    student = make_student()
    course = make_course()
    before = snapshot(student, course)
    register_course(student, course)
    assert withdraw_course(student, course) is True
    assert (student, course) == before


def test_ST09_withdraw_when_not_registered():
    student = make_student(registered_courses={"MATH201"})
    course = make_course()
    before = snapshot(student, course)
    assert withdraw_course(student, course) is False
    assert (student, course) == before
