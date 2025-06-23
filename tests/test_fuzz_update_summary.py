import datetime
import importlib
import json
import os
import string
import tempfile
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

import app.config as config
import app.utils.db as db
import app.utils.scheduling as scheduling

LETTERS = string.ascii_letters + string.digits + string.punctuation + " "


@st.composite
def template_strategy(draw):
    name = draw(st.text(string.ascii_letters, min_size=1, max_size=10))
    groups = draw(
        st.text(string.ascii_lowercase, min_size=1, max_size=5).map(
            lambda s: ",".join(s)
        )
    )
    last_caption_time = draw(
        st.datetimes(
            min_value=datetime.datetime(2023, 1, 1),
            max_value=datetime.datetime(2023, 12, 31, 23, 59, 59),
        ).map(lambda d: d.strftime("%Y-%m-%d %H:%M:%S"))
    )
    notes = draw(st.text(LETTERS, min_size=0, max_size=100))
    last_caption = draw(st.text(LETTERS, min_size=0, max_size=200))
    return {
        "name": name,
        "groups": groups,
        "last_caption_time": last_caption_time,
        "notes": notes,
        "last_caption": last_caption,
    }


@st.composite
def template_edge_strategy(draw):
    tpl = draw(template_strategy())
    if draw(st.booleans()):
        tpl["groups"] += ",private"
    opt = draw(st.integers(min_value=0, max_value=2))
    if opt == 0:
        tpl.pop("last_caption_time", None)
    elif opt == 1:
        tpl["last_caption_time"] = ""
    elif opt == 2:
        dt = datetime.datetime.utcnow() - datetime.timedelta(
            hours=draw(st.integers(min_value=4, max_value=24))
        )
        tpl["last_caption_time"] = dt.strftime("%Y-%m-%d %H:%M:%S")
    if draw(st.booleans()):
        tpl["notes"] *= draw(st.integers(min_value=2, max_value=4))
    if draw(st.booleans()):
        tpl["last_caption"] *= draw(st.integers(min_value=2, max_value=4))
    return tpl


summary_strategy = st.one_of(
    st.text(string.ascii_letters + string.digits, min_size=1, max_size=50),
    st.dictionaries(
        st.integers(min_value=0, max_value=3).map(str),
        st.text(string.ascii_letters, min_size=1, max_size=5),
        min_size=1,
        max_size=3,
    ).map(json.dumps),
)


@given(
    templates=st.dictionaries(
        st.text(min_size=1, max_size=10), template_strategy(), min_size=1, max_size=10
    ),
    summary=summary_strategy,
)
@settings(max_examples=20)
def test_fuzz_update_summary(templates, summary):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with patch.dict(os.environ, {"GLIMPSER_DATABASE_PATH": db_path}):
            importlib.reload(config)
            importlib.reload(db)
            import app.models as models

            importlib.reload(models)
            importlib.reload(models.summary)
            importlib.reload(scheduling)
            db.init_db()
            scheduling.SessionLocal = db.SessionLocal

            with (
                patch(
                    "app.utils.scheduling.get_templates_sorted_by_last_caption_time",
                    return_value=list(templates.items()),
                ),
                patch("app.utils.scheduling.summarize", return_value=summary),
            ):
                scheduling.update_summary()


@given(
    templates=st.dictionaries(
        st.text(min_size=1, max_size=10),
        template_edge_strategy(),
        min_size=1,
        max_size=10,
    ),
    summary=summary_strategy,
)
@settings(max_examples=20)
def test_fuzz_update_summary_edge_cases(templates, summary):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with patch.dict(os.environ, {"GLIMPSER_DATABASE_PATH": db_path}):
            importlib.reload(config)
            importlib.reload(db)
            import app.models as models

            importlib.reload(models)
            importlib.reload(models.summary)
            importlib.reload(scheduling)
            db.init_db()
            scheduling.SessionLocal = db.SessionLocal

            with (
                patch(
                    "app.utils.scheduling.get_templates_sorted_by_last_caption_time",
                    return_value=list(templates.items()),
                ),
                patch("app.utils.scheduling.summarize", return_value=summary),
            ):
                scheduling.update_summary()
