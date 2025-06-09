# Dark Mode Support

Glimpser starts in dark mode for new users, storing the preference in
`localStorage`. You can switch to light mode at any time with the theme
toggle. The CSS defines variables for background and text colors with light and
dark variants, so forms and tables remain readable in both themes.

You can force the interface into light or dark mode using the toggle on the
settings page. The switch stores your choice in `localStorage` so your
preference persists across visits and is applied to every page you load.

A new `--table-border-color` variable controls table outlines. Dark mode
defaults to a subtle `#444` while the light theme overrides it to `#ddd`.
The settings page now uses this variable for its forms and tables so fields
look consistent regardless of color scheme.

Hyperlinks also switch to a lighter blue in dark mode so links remain legible on
the dark background.

The captions page uses the same theme variables. Prompt and response fields now
inherit `--form-bg-color` and `--form-text-color` so text remains legible when
switching themes. Each caption row labels the prompt and last caption so the
conversation thread is obvious, and the prompt textarea shows a placeholder to
encourage editing.
