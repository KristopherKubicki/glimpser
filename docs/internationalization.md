# Internationalization

Glimpser uses [Flask-Babel](https://flask-babel.tkte.ch/) for translations. The
`LANG` setting determines the default locale. Translation files live in the
`translations/` directory and can be updated with `pybabel`:

```sh
pybabel extract -F babel.cfg -o messages.pot .
pybabel init -i messages.pot -d translations -l fr
pybabel compile -d translations
```

Wrap user‑visible strings in templates with `{{ _('text') }}` or in Python using
`gettext`. Provide a `messages.po` for each locale and rebuild after edits.
