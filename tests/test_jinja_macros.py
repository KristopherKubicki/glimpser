import unittest
from jinja2 import Environment, FileSystemLoader


class TestJinjaMacros(unittest.TestCase):
    """Ensure Jinja macros render expected markup."""

    def setUp(self):
        self.env = Environment(loader=FileSystemLoader("app/templates"))

    def test_confirm_modal_ids(self):
        template = self.env.get_template("components.html")
        html = template.module.confirm_modal("remove")
        self.assertIn('id="remove-modal"', html)
        self.assertIn('id="remove-confirm"', html)
        self.assertIn('id="remove-cancel"', html)

    def test_card_wraps_content(self):
        tmpl = self.env.from_string(
            '{% from "components.html" import card %}{% call card("Title") %}Body{% endcall %}'
        )
        html = tmpl.render()
        self.assertIn('<div class="card">', html)
        self.assertIn('<div class="card-header">Title</div>', html)
        self.assertIn('<div class="card-body">Body</div>', html)


if __name__ == "__main__":
    unittest.main()
