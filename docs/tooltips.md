# UI and Navigation Tooltips

This document lists the main tooltips available in the Glimpser interface. Hovering over controls reveals short explanations of their function.

## Navigation Bar

- **Home** – returns to the dashboard.
- **Group links** – open the page listing cameras in that group.
- **Template title** – links to the template details page.
- **System Performance icon** – shows CPU, memory and other metrics. It hides
  when the system is healthy unless `HEALTH_STATUS_ALWAYS_VISIBLE` is set.
- **Danger Mode icon** – appears only when Danger mode is available. Hovering over it explains why the feature may be disabled.
- **Discover Cameras icon** – opens the Settings page to the Discover tab.
- **Captions icon** – reads and updates camera language models. The icon flashes
  with the latest caption when group messages arrive. After a short period of
  inactivity the newest global summary slowly scrolls across the top in gray text
  and remains visible until the next caption arrives. The `CHYRON_SPEED` setting
  controls how long the message scrolls and defaults to `0` so the banner is hidden.
  Clicking the chyron opens the `/captions` page. It stays green for one minute after the
  most recent caption, turns yellow for the next five minutes and becomes red
  when no update has been received for over thirty minutes.
- **Clock icon** – opens the live page with instructions for real‑time streaming.
- **Settings gear icon** – opens the settings page.
- **Login link** – appears when not authenticated.

## Footer

- **Help** – opens this documentation.
- **Version** – indicates the installed package version and warns when updates are available.
- **About/License** – links to project information.
- The footer itself hides when the mouse is inactive.

These tooltips aim to make the interface self‑explanatory and easier to navigate.

## Forms

Interactive forms now include additional tooltips:

- **Add Camera** – describes each field on the Discover tab and the "Structured" XPath buttons. A short helper paragraph guides you to test the URL and open the Advanced Options section.
- **URL tester** – a tooltip shows "checking" then "valid" or "invalid" next to the URL field.
- **Template Details** – buttons like "Suggest Prompt" and "Suggest Fix" describe their actions.
- **Template toolbar** – quick actions appear at the bottom-left of the details page and fade out when idle.
- **Captions** – upload and filter controls have descriptive titles. The metric dropdown filters feeds by count or storage and updates the list immediately.
- **Danger Mode** – the checkbox, save button and modal controls all include tooltips.
- **Live video player** – tooltip now refreshes with the full caption as it updates.
- **Group selector** – choose a group on the live page. Selecting one reveals a second dropdown for cameras and syncs with the navigation bar.
- **Info icon** – toggles camera metadata on the live page.
- **Feed status indicators** – on the Status page, red or yellow dots display a tooltip with offline time and the latest log message.
- **Camera type icons** – small symbols next to each feed name show whether the capture runs in a full browser, headless mode, or uses stealth.
- **Chat modal controls** – the close icon and submit button now describe their actions.
- **Help page tabs** – each tab button explains what information the section contains.
- **Settings tabs** – hovering shows which category will open.
- **Cost dashboards** – date selectors, the Load buttons and range slider include titles.
- **LLM_PROMPT settings** – tooltips explain that the caption and summary prompts
  support `$datetime` and can span multiple lines.

## Dynamic Tooltips

A small JavaScript helper now displays a custom tooltip when hovering or focusing on any element with a `title` attribute. These tooltips track the mouse cursor and update automatically when the `title` text changes, giving live feedback across the interface.

To avoid the browser's default tooltip from also appearing, the script now temporarily removes the `title` attribute while showing the custom tooltip and restores it on mouseout.
