"""Terminal dashboard for feed status."""

from __future__ import annotations

import curses

from .scheduling import get_feed_status

REFRESH_INTERVAL = 5


def _render(screen: curses.window) -> None:
    """Render the feed dashboard until ``q`` is pressed."""
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_YELLOW, -1)
    curses.init_pair(3, curses.COLOR_RED, -1)

    screen.timeout(REFRESH_INTERVAL * 1000)

    while True:
        feeds = get_feed_status()
        height, width = screen.getmaxyx()
        screen.erase()
        screen.addstr(0, 0, "Glimpser Feed Dashboard (press q to quit)"[: width - 1])
        header = f"{'Name':20} {'Status':8} {'Last Image':14} {'Last Caption':14}"
        screen.addstr(1, 0, header[: width - 1])

        for idx, feed in enumerate(feeds, start=2):
            if idx >= height:
                break
            row = (
                f"{feed['name']:<20} {feed['status']:<8} "
                f"{(feed['last_screenshot_display'] or '-'):14} "
                f"{(feed['last_caption_display'] or '-'):14}"
            )
            color = curses.color_pair(1)
            if feed["status"] == "slow":
                color = curses.color_pair(2)
            elif feed["status"] == "error":
                color = curses.color_pair(3)
            screen.addstr(idx, 0, row[: width - 1], color)

        screen.refresh()
        ch = screen.getch()
        if ch in (ord("q"), ord("Q")):
            return


def main() -> None:
    """Entry point for ``glimpser-dashboard``."""
    curses.wrapper(_render)


if __name__ == "__main__":
    main()
