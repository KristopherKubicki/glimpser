import os
import sys
from pathlib import Path
from html.parser import HTMLParser
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TemplateParser(HTMLParser):
    """Simple HTML parser to capture img tags and form inputs."""

    def __init__(self):
        super().__init__()
        self.img_tags = []
        self.link_tags = []
        self.forms = []
        self._current_form = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "img":
            self.img_tags.append(attrs_dict)
        elif tag == "link":
            self.link_tags.append(attrs_dict)
        elif tag == "form":
            self._current_form = {"attrs": attrs_dict, "inputs": []}
            self.forms.append(self._current_form)
        elif tag in {"input", "textarea", "select"} and self._current_form is not None:
            self._current_form["inputs"].append(attrs_dict)

    def handle_endtag(self, tag):
        if tag == "form":
            self._current_form = None


def parse_template(path: Path) -> TemplateParser:
    parser = TemplateParser()
    with open(path, encoding="utf-8") as f:
        parser.feed(f.read())
    return parser


class TestHtmlTemplates(unittest.TestCase):
    def test_img_tags_have_alt(self):
        templates_dir = Path("app/templates")
        for template in templates_dir.glob("*.html"):
            parser = parse_template(template)
            for attrs in parser.img_tags:
                with self.subTest(template=template, attrs=attrs):
                    self.assertIn("alt", attrs)
                    self.assertTrue(attrs["alt"].strip())

    def test_login_form_inputs(self):
        parser = parse_template(Path("app/templates/login.html"))
        self.assertTrue(parser.forms, "login.html should contain a form")
        inputs = {i.get("name") for i in parser.forms[0]["inputs"]}
        self.assertIn("username", inputs)
        self.assertIn("password", inputs)

    def test_discover_add_camera_form_inputs(self):
        parser = parse_template(Path("app/templates/_discover_tab.html"))
        add_form = None
        for form in parser.forms:
            if form["attrs"].get("id") == "add-template-form":
                add_form = form
                break
        self.assertIsNotNone(add_form, "add-template-form missing")
        inputs = {i.get("id") or i.get("name") for i in add_form["inputs"]}
        required = {"name", "url", "frequency", "timeout"}
        self.assertTrue(required.issubset(inputs))

    def test_header_preloads_sprite(self):
        parser = parse_template(Path("app/templates/header.html"))
        expected_href = "{{ url_for('static', filename='icons/sprite.svg') }}"
        for attrs in parser.link_tags:
            if (
                attrs.get("rel") == "preload"
                and attrs.get("as") == "image"
                and attrs.get("type") == "image/svg+xml"
                and "crossorigin" in attrs
                and attrs.get("href") == expected_href
            ):
                break
        else:
            self.fail("sprite.svg preload link missing")


if __name__ == "__main__":
    unittest.main()
