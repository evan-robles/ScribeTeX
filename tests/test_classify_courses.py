from scribetex.classify import course_slug, match_course

KNOWN = ["MATH 257 Linear Algebra", "CHEM 20100 Inorganic Chemistry I"]


def test_course_slug():
    assert course_slug("MATH 257 Linear Algebra") == "MATH-257-Linear-Algebra"
    assert course_slug("  Weird!! name??  ") == "Weird-name"


def test_high_confidence_exact_token():
    course, conf = match_course("linear algebra", KNOWN)
    assert course == "MATH 257 Linear Algebra"
    assert conf == "high"


def test_high_confidence_by_number():
    course, conf = match_course("math 257", KNOWN)
    assert course == "MATH 257 Linear Algebra"
    assert conf == "high"


def test_no_match_is_new():
    course, conf = match_course("Organic Chemistry", KNOWN)
    assert course is None
    assert conf == "none"


def test_ambiguous_is_low():
    known = ["MATH 257 Linear Algebra", "MATH 258 Linear Algebra II"]
    course, conf = match_course("linear algebra", known)
    assert conf == "low"
