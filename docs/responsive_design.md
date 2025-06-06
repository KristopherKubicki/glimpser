# Responsive Design

Glimpser now adapts to phones and tablets. Tables reflow vertically to avoid horizontal scrolling and video grids automatically switch to a single column when viewed on devices without hover capability or small viewports. The navigation menu stays expanded on small screens except for the Settings page where it collapses into a hamburger button.

The main template view scales thumbnails with the width slider and the page now uses smooth scrolling for longer lists. Previews resize by adjusting their width and height, ensuring the full image remains visible without shifting or cropping. When a group is opened, the slider defaults to the smallest width that keeps all cameras visible without scrolling.

The header navigation also uses smaller padding so it stays out of the way on both mobile and desktop.

Group links in the header are now available through a dropdown menu. The list
populates asynchronously from the `/groups` endpoint and fits neatly inside the
hamburger layout on small screens.

Selecting a group from that dropdown while on the **Live** page now updates the
camera selector immediately without reloading the page, keeping navigation
seamless.

Offline preview keeps recently viewed pages and assets in the browser cache so the interface remains responsive even on poor connections. This feature is enabled automatically.
