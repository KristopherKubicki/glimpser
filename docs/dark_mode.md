# Dark Mode Support

Glimpser's interface now adapts to your system's preferred color scheme and
defaults to dark mode. The CSS defines variables for background and text colors
with light and dark variants. Forms and tables use these variables so elements
remain readable in both themes.

Dark mode is the recommended scheme. You can customize the look by overriding
the provided CSS variables:

```css
:root {
    --bg-color: #1a1a1a;
    --text-color: #eaeaea;
}
```

Ensure that contrast ratios stay above accessibility guidelines when adjusting
colors.
