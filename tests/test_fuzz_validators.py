import os
import string

from hypothesis import given, settings
from hypothesis import strategies as st

from app.utils.validators import (
    validate_setting,
    validate_template_name,
    validate_update_data,
)

LETTERS = string.ascii_letters + string.digits + string.punctuation + " \n\r"
MAX_EXAMPLES = int(os.getenv("HYPOTHESIS_MAX_EXAMPLES", "50"))


@given(
    name=st.sampled_from(
        ["PORT", "LOG_LEVEL", "EMAIL_SENDER", "EMAIL_RECIPIENTS", "CUSTOM"]
    ),
    value=st.text(LETTERS, min_size=0, max_size=10),
)
@settings(max_examples=MAX_EXAMPLES)
def test_fuzz_validate_setting(name: str, value: str) -> None:
    validate_setting(name, value)


@st.composite
def update_data_strategy(draw):
    keys = [
        "frequency",
        "timeout",
        "rollback_frames",
        "object_confidence",
        "motion",
        "notes",
        "groups",
        "proxy",
    ]
    data = {"url": "http://example"}
    for key in keys:
        if key in {"frequency", "timeout", "rollback_frames"}:
            val = draw(
                st.one_of(
                    st.integers(-1000, 100000).map(str),
                    st.text(LETTERS, min_size=0, max_size=5),
                )
            )
        elif key in {"object_confidence", "motion"}:
            val = draw(
                st.one_of(
                    st.floats(-5, 5).map(str),
                    st.text(LETTERS, min_size=0, max_size=5),
                )
            )
        else:
            val = draw(st.text(LETTERS, min_size=0, max_size=10))
        data[key] = val
    return data


@given(data=update_data_strategy())
@settings(max_examples=MAX_EXAMPLES)
def test_fuzz_validate_update_data(data: dict) -> None:
    validate_update_data(data)


@given(name=st.text(LETTERS, min_size=0, max_size=40))
@settings(max_examples=MAX_EXAMPLES)
def test_fuzz_validate_template_name(name: str) -> None:
    validate_template_name(name)
