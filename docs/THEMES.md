Users can change the look of the app from Settings without any code change. Themes are built in Phase 1 so every later screen uses them.
Options (all independent)
• Mode: Light, Dark, or Match Windows (default).
• Palette: Ocean (blue, default), Forest (green), Sunset (amber), Slate (neutral gray), Plum (purple).
• Density: Comfortable (default) or Compact, which changes table row height and spacing.
• Text size: Small, Medium (default), Large.
• Brand colour: optional hex set in Settings that overrides the palette accent, so the app can match the company colour.
Implementation rules
1.  All colours come from CSS custom properties defined once in a theme stylesheet (surface, raised surface, border, three text levels, accent, soft accent, success, warning, danger and their soft backgrounds). No hardcoded colours anywhere else.
2.  A theme is a combination of data-mode, data-palette, data-density and data-text-size attributes on the root element. Switching applies instantly with no reload.
3.  Status colours (occupied, vacant, reserved, paid, overdue) keep their meaning in every palette. Only the accent changes with the palette.
4.  Every palette must pass a readable-contrast check (at least 4.5 to 1 for body text) in both light and dark mode, verified by a script or test.
5.  Charts read their colours from the same variables and use labels or shapes in addition to colour.
6.  The choice is saved per user. The company brand colour and the default palette for new users live in Settings.
7.  PDFs (invoices, receipts, statements) always use a fixed print-safe light style with the company logo and brand colour, never the dark theme.
8.  Thermal receipts are plain text and ignore themes.
9.  Settings has an Appearance screen with a live preview card (a mini dashboard) so users see changes before saving.