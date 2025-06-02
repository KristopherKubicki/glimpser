# Right-to-Left Layout Support

Glimpser's styles now use logical CSS properties for margins and padding. Rules
such as `margin-inline-start` and `margin-inline-end` replace `margin-left` and
`margin-right`. Likewise, `padding-inline-start` and `padding-inline-end` are
used instead of the old directional properties. These logical properties switch
automatically when the page uses `dir="rtl"`, allowing right-to-left themes
without extra markup or scripts.
