import os
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path


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

    def test_login_placeholders(self):
        parser = parse_template(Path("app/templates/login.html"))
        placeholders = {i.get("placeholder") for i in parser.forms[0]["inputs"]}
        self.assertIn("Username", placeholders)
        self.assertIn("Password", placeholders)

    def test_login_has_remember_checkbox(self):
        parser = parse_template(Path("app/templates/login.html"))
        inputs = [i for i in parser.forms[0]["inputs"] if i.get("name") == "remember"]
        self.assertTrue(inputs, "remember checkbox missing")
        self.assertEqual(inputs[0].get("type"), "checkbox")

    def test_discover_add_camera_form_inputs(self):
        html = Path("app/templates/_discover_tab.html").read_text(encoding="utf-8")
        self.assertIn("template_form(", html)

    def test_discover_has_existing_map_variable(self):
        with open("app/templates/_discover_tab.html", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("existingMap", html)

    def test_discover_table_sortable(self):
        html = Path("app/templates/_discover_tab.html").read_text(encoding="utf-8")
        self.assertIn('<table id="discover-table"', html)
        self.assertIn('th class="sortable"', html)

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

    def test_settings_has_advanced_toggle(self):
        parser = parse_template(Path("app/templates/settings.html"))
        inputs = [i for form in parser.forms for i in form["inputs"]]
        advanced = next((i for i in inputs if i.get("id") == "advanced-toggle"), None)
        self.assertIsNotNone(advanced, "advanced-toggle missing")
        self.assertEqual(advanced.get("type"), "checkbox")

    def test_captions_prompt_label(self):
        """Captions page prompt textarea should have a visible label."""
        html = Path("app/templates/captions.html").read_text(encoding="utf-8")
        self.assertIn("Prompt</label>", html)
        self.assertIn("Last caption", html)

    def test_edit_template_frequency_min(self):
        html = Path("app/templates/template_details.html").read_text(encoding="utf-8")
        self.assertIn("template_form(", html)
        components = Path("app/templates/components.html").read_text(encoding="utf-8")
        self.assertIn('min="0"', components)
        self.assertIn('datalist id="object-filter-options"', components)

    def test_groups_field_has_datalist(self):
        components = Path("app/templates/components.html").read_text(encoding="utf-8")
        self.assertIn('id="groups"', components)
        self.assertIn('datalist id="group-options"', components)

    def test_object_filter_gpu_icon_present(self):
        components = Path("app/templates/components.html").read_text(encoding="utf-8")
        self.assertIn("object-gpu-status", components)

    def test_status_tab_has_sparklines(self):
        html = Path("app/templates/_status_tab.html").read_text(encoding="utf-8")
        self.assertIn('id="memory-sparkline"', html)
        self.assertIn('id="disk-sparkline"', html)

    def test_status_tab_thread_list(self):
        html = Path("app/templates/_status_tab.html").read_text(encoding="utf-8")
        self.assertIn('<table id="thread-table"', html)

    def test_index_has_control_labels(self):
        """Dashboard search and slider inputs should have labels."""
        html = Path("app/templates/components.html").read_text(encoding="utf-8")
        self.assertIn('label for="search-input"', html)
        self.assertIn('label for="grid-width-slider"', html)

    def test_grid_presets_present(self):
        html = Path("app/templates/components.html").read_text(encoding="utf-8")
        self.assertIn('id="grid-presets"', html)
        self.assertIn('data-grid="4"', html)


if __name__ == "__main__":
    unittest.main()
