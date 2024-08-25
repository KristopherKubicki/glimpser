import unittest
import random
import string
from unittest.mock import patch
from app.utils.scheduling import update_summary


class TestFuzzUpdateSummary(unittest.TestCase):
    @patch("app.utils.scheduling.get_templates")
    @patch("app.utils.scheduling.summarize")
    def test_fuzz_update_summary(self, mock_summarize, mock_get_templates):
        # Number of fuzz test iterations
        num_iterations = 100

        for _ in range(num_iterations):
            # Generate random templates
            num_templates = random.randint(1, 10)
            templates = {}
            for i in range(num_templates):
                template = self.generate_random_template()
                templates[f"template_{i}"] = template

            # Mock get_templates to return our random templates
            mock_get_templates.return_value = templates

            # Mock summarize to return a random string
            mock_summarize.return_value = "".join(
                random.choices(string.ascii_letters + string.digits, k=50)
            )

            # Call the function under test
            try:
                update_summary()
            except Exception as e:
                self.fail(
                    f"update_summary raised {type(e).__name__} unexpectedly: {str(e)}"
                )

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


if __name__ == "__main__":
    unittest.main()
