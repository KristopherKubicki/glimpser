# Danger Mode Setup and Usage

Danger mode allows Glimpser to leverage your existing Chrome session for capturing dynamic sites. When active, Glimpser attaches to a local Chrome instance running with the `--remote-debugging-port=9222` flag. This is useful for pages that require an authenticated session or user context.

## Enabling Remote Debugging

1. **Launch Chrome with the debugging port open.** The exact command varies by platform:
   - **Linux**: `google-chrome --remote-debugging-port=9222`
   - **macOS**: `open /Applications/Google\ Chrome.app --args --remote-debugging-port=9222`
   - **Windows**: modify your Chrome shortcut to append `--remote-debugging-port=9222` to the *Target* field.
2. Leave this Chrome window running. Glimpser will connect to the existing instance when the port is detected.

If Chrome is not started with this flag, Danger mode will be unavailable.

## Shortcut Update Options

After Chrome updates, shortcuts may revert to their original command line. Two approaches can help keep the debug port enabled:

- **Manual update**: Edit the desktop shortcut each time Chrome updates.
- **Helper script**: Run `python scripts/update_chrome_shortcut.py` to rewrite the shortcut with the required flag. This can also be triggered from the *Update Chrome Shortcut* button on the Settings page.

For now, you can store the launch command in a script and double-click it instead of using the original shortcut.

## Using Danger Mode in Glimpser

When Chrome's debug port is open and no user input has been detected for a short period, Glimpser shows an orange indicator in the navigation bar. A `!` appears in the icon when ready and an `×` explains why it's disabled when you hover over it.

Captures marked as "Danger" in the template editor will use your running Chrome session. Glimpser opens a new tab, performs the capture, and closes the tab when finished. It skips the operation if you become active while the capture is pending.

Be cautious with this feature, as it can interact with your browser while you are away. Ensure you trust the pages being captured.

The UI exposes a global `window.dangerActive` property that reflects when Danger mode is ready. This property is typed as a boolean so assigning anything else throws an error in strict mode.
