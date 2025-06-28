# Search Autocomplete

The search field can provide suggestions based on available documentation pages. Start typing a keyword to see matching results immediately.

Autocomplete triggers after two characters and highlights results in real time. Selecting a suggestion jumps straight to the corresponding page.

The dashboard search box now suggests camera or group names as you type. The
input field queries a new `/search_suggestions` endpoint and displays up to ten
matching results. This makes locating specific cameras much faster on large
installations.

Documentation titles are now included in these suggestions as well. Typing a
topic like "offline" will show the matching docs page in addition to any camera
or group names. Selecting the doc entry takes you straight to `/docs/<page>.md`.
