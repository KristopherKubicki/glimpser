import random
import string
import unittest

from app.utils.validators import (
    validate_setting,
    validate_template_name,
    validate_update_data,
)


class TestFuzzValidators(unittest.TestCase):
    def random_string(self, min_len: int = 0, max_len: int = 20) -> str:
        length = random.randint(min_len, max_len)
        chars = string.ascii_letters + string.digits + string.punctuation + " \n\r"
        return "".join(random.choices(chars, k=length))

    def test_fuzz_validate_setting(self):
        names = ["PORT", "LOG_LEVEL", "EMAIL_SENDER", "EMAIL_RECIPIENTS", "CUSTOM"]
        for _ in range(100):
            name = random.choice(names)
            value = self.random_string(0, 10)
            try:
                validate_setting(name, value)
            except Exception as e:
                self.fail(
                    f"validate_setting({name!r}, {value!r}) raised {type(e).__name__}: {e}"
                )

    def test_fuzz_validate_update_data(self):
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
        for _ in range(100):
            data = {"url": "http://example"}
            for key in keys:
                if key in {"frequency", "timeout", "rollback_frames"}:
                    if random.random() < 0.5:
                        data[key] = str(random.randint(-1000, 100000))
                    else:
                        data[key] = self.random_string(0, 5)
                elif key in {"object_confidence", "motion"}:
                    if random.random() < 0.5:
                        data[key] = str(random.uniform(-5, 5))
                    else:
                        data[key] = self.random_string(0, 5)
                else:
                    data[key] = self.random_string(0, 10)
            try:
                validate_update_data(data)
            except Exception as e:
                self.fail(
                    f"validate_update_data raised {type(e).__name__} for {data}: {e}"
                )

    def test_fuzz_validate_template_name(self):
        for _ in range(100):
            name = self.random_string(0, 40)
            try:
                validate_template_name(name)
            except Exception as e:
                self.fail(
                    f"validate_template_name({name!r}) raised {type(e).__name__}: {e}"
                )


if __name__ == "__main__":
    unittest.main()
