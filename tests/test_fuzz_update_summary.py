import datetime
import importlib
import json
import os
import random
import string
import tempfile
import unittest
from unittest.mock import patch

import app.config as config
import app.utils.db as db
import app.utils.scheduling as scheduling


class TestFuzzUpdateSummary(unittest.TestCase):
    def test_fuzz_update_summary(self):
        num_iterations = 100

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            env_patch = patch.dict(os.environ, {"GLIMPSER_DATABASE_PATH": db_path})
            env_patch.start()
            importlib.reload(config)
            importlib.reload(db)
            import app.models as models

            importlib.reload(models)
            importlib.reload(models.summary)
            importlib.reload(scheduling)
            db.init_db()
            scheduling.SessionLocal = db.SessionLocal

            for _ in range(num_iterations):
                num_templates = random.randint(1, 10)
                templates = {
                    f"template_{i}": self.generate_random_template()
                    for i in range(num_templates)
                }

                with (
                    patch(
                        "app.utils.scheduling.get_templates_sorted_by_last_caption_time",
                        return_value=list(templates.items()),
                    ),
                    patch(
                        "app.utils.scheduling.summarize",
                        return_value="".join(
                            random.choices(string.ascii_letters + string.digits, k=50)
                        ),
                    ),
                ):
                    try:
                        scheduling.update_summary()
                    except Exception as e:
                        env_patch.stop()
                        self.fail(
                            f"update_summary raised {type(e).__name__} unexpectedly: {str(e)}"
                        )
            env_patch.stop()

    def generate_random_template(self):
        return {
            "name": "".join(random.choices(string.ascii_letters, k=10)),
            "groups": ",".join(
                random.choices(string.ascii_lowercase, k=random.randint(1, 5))
            ),
            "last_caption_time": f"2023-{random.randint(1,12):02d}-{random.randint(1,28):02d} {random.randint(0,23):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}",
            "notes": "".join(
                random.choices(
                    string.ascii_letters + string.digits + string.punctuation + " ",
                    k=random.randint(0, 100),
                )
            ),
            "last_caption": "".join(
                random.choices(
                    string.ascii_letters + string.digits + string.punctuation + " ",
                    k=random.randint(0, 200),
                )
            ),
        }

    def generate_random_template_edge(self):
        template = self.generate_random_template()
        if random.random() < 0.3:
            template["groups"] += ",private"
        rand = random.random()
        if rand < 0.2:
            template.pop("last_caption_time", None)
        elif rand < 0.4:
            template["last_caption_time"] = ""
        elif rand < 0.6:
            dt = datetime.datetime.utcnow() - datetime.timedelta(
                hours=random.randint(4, 24)
            )
            template["last_caption_time"] = dt.strftime("%Y-%m-%d %H:%M:%S")
        if random.random() < 0.2:
            template["notes"] *= random.randint(2, 4)
        if random.random() < 0.2:
            template["last_caption"] *= random.randint(2, 4)
        return template

    def random_summary(self):
        if random.random() < 0.5:
            entries = {
                str(i): "".join(random.choices(string.ascii_letters, k=5))
                for i in range(random.randint(1, 3))
            }
            return json.dumps(entries)
        return "".join(random.choices(string.ascii_letters + string.digits, k=50))

    def test_fuzz_update_summary_edge_cases(self):
        num_iterations = 100

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            env_patch = patch.dict(os.environ, {"GLIMPSER_DATABASE_PATH": db_path})
            env_patch.start()
            importlib.reload(config)
            importlib.reload(db)
            import app.models as models

            importlib.reload(models)
            importlib.reload(models.summary)
            importlib.reload(scheduling)
            db.init_db()
            scheduling.SessionLocal = db.SessionLocal

            for _ in range(num_iterations):
                num_templates = random.randint(1, 10)
                templates = {
                    f"template_{i}": self.generate_random_template_edge()
                    for i in range(num_templates)
                }

                with (
                    patch(
                        "app.utils.scheduling.get_templates_sorted_by_last_caption_time",
                        return_value=list(templates.items()),
                    ),
                    patch(
                        "app.utils.scheduling.summarize",
                        side_effect=lambda *a, **k: self.random_summary(),
                    ),
                ):
                    try:
                        scheduling.update_summary()
                    except Exception as e:
                        env_patch.stop()
                        self.fail(
                            f"update_summary raised {type(e).__name__} unexpectedly: {str(e)}"
                        )
            env_patch.stop()


if __name__ == "__main__":
    unittest.main()
