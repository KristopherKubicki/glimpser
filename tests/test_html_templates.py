import unittest
from html.parser import HTMLParser
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


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

    def test_login_error_has_alert_role(self):
        html = Path("app/templates/login.html").read_text(encoding="utf-8")
        self.assertIn('id="login-error"', html)
        self.assertIn('role="alert"', html)
        self.assertIn('aria-live="assertive"', html)

    def test_login_inputs_described_by_error(self):
        parser = parse_template(Path("app/templates/login.html"))
        username = next(
            i for i in parser.forms[0]["inputs"] if i.get("id") == "username"
        )
        password = next(
            i for i in parser.forms[0]["inputs"] if i.get("id") == "password"
        )
        self.assertEqual(username.get("aria-describedby"), "login-error")
        self.assertEqual(password.get("aria-describedby"), "login-error")

    def test_login_has_recovery_note(self):
        html = Path("app/templates/login.html").read_text(encoding="utf-8")
        self.assertIn('id="recovery-note"', html)
        self.assertIn("generate_credentials.py", html)

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

    def test_settings_has_contrast_toggle(self):
        html = Path("app/templates/settings.html").read_text(encoding="utf-8")
        self.assertIn('id="contrast-toggle"', html)

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

    def test_template_form_error_container(self):
        components = Path("app/templates/components.html").read_text(encoding="utf-8")
        self.assertIn('id="template-error"', components)
        self.assertIn('role="alert"', components)

    def test_groups_field_has_datalist(self):
        components = Path("app/templates/components.html").read_text(encoding="utf-8")
        self.assertIn('id="groups"', components)
        self.assertIn('datalist id="group-options"', components)

    def test_object_filter_gpu_icon_present(self):
        components = Path("app/templates/components.html").read_text(encoding="utf-8")
        self.assertIn("object-gpu-status", components)

    def test_browser_checkbox_present(self):
        components = Path("app/templates/components.html").read_text(encoding="utf-8")
        self.assertIn('id="browser"', components)

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

    def test_settings_row_macro_renders(self):
        env = Environment(loader=FileSystemLoader("app/templates"))
        tmpl = env.from_string(
            '{% from "components.html" import settings_row with context %}{{ settings_row(setting) }}'
        )
        context = {
            "setting": {"name": "TEST_BOOL", "value": "True"},
            "boolean_fields": {"TEST_BOOL"},
            "numeric_fields": set(),
            "choices": {},
            "placeholders": {},
            "locked_settings": set(),
            "tooltips": {},
            "metrics": {"ffmpeg_gpu_support": True},
        }
        html = tmpl.render(**context)
        self.assertIn("<tr>", html)
        self.assertIn('name="TEST_BOOL"', html)
        self.assertIn('type="checkbox"', html)

    def test_player_camera_name_has_live_status(self):
        html = Path("app/templates/player.html").read_text(encoding="utf-8")
        self.assertIn('id="camera-name"', html)
        self.assertIn('role="status"', html)
        self.assertIn('aria-live="polite"', html)

    def test_logs_status_has_live_region(self):
        html = Path("app/templates/logs.html").read_text(encoding="utf-8")
        self.assertIn('id="log-connection-status"', html)
        self.assertIn('role="status"', html)
        self.assertIn('aria-live="polite"', html)

    def test_index_time_live_region(self):
        html = Path("app/templates/index.html").read_text(encoding="utf-8")
        self.assertIn('id="index-time"', html)
        self.assertIn('role="timer"', html)
        self.assertIn('aria-live="polite"', html)

    def test_live_page_has_overlay(self):
        html = Path("app/templates/live.html").read_text(encoding="utf-8")
        self.assertIn('id="video-overlay"', html)
        self.assertIn('id="loading-indicator"', html)

    def test_live_page_has_fullscreen_button(self):
        html = Path("app/templates/live.html").read_text(encoding="utf-8")
        self.assertIn('id="fullscreen-toggle"', html)


if __name__ == "__main__":
    unittest.main()
