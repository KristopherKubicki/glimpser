# Responsive Design

Glimpser now adapts to phones and tablets. Tables reflow vertically to avoid horizontal scrolling and video grids automatically switch to a single column on touch devices with small screens. The navigation menu stays expanded on small screens and does not show the hamburger button except on the Settings page where collapsing the menu helps conserve space. JavaScript ensures the menu remains open elsewhere so mobile users can quickly access links.

The main template view scales thumbnails with a width slider on desktop screens and the page now uses smooth scrolling for longer lists. Previews resize by adjusting their width and height, ensuring the full image remains visible without shifting or cropping. Tiles now center each player with flexbox so videos shrink to fit on narrow screens without cropping. Camera detail views enforce a 16:9 aspect ratio so the player scales consistently across phones, tablets and desktops. When a group is opened, the slider defaults to the smallest width that keeps all cameras visible without scrolling. On narrow devices, the slider hides automatically to keep the interface simple. Mobile tiles still show the last screenshot and start playing live video after a brief hold.

The header navigation also uses smaller padding so it stays out of the way on both mobile and desktop.
The main content now has less top padding so on‑page controls like the search bar sit closer to the navigation.
The template control panel now compresses on phones with Search, Play All and Sort in one row while the status legend hides.
The header navigation also uses smaller padding so it stays out of the way on both mobile and desktop. The header now sticks to the top of the screen as you scroll so navigation is always accessible.
The footer now condenses on small screens by hiding the copyright notice and build information, leaving only the essential navigation links.
The header navigation collapses into a stacked menu on small screens. Links grow larger with extra padding so they're easier to tap. The clock, scrolling caption chyron and temporary flash messages are all hidden on phones to maximize space.

Group links in the header are now available through a dropdown menu when logged
in. The list populates asynchronously from the `/groups` endpoint and fits
neatly inside the hamburger layout on small screens.

Selecting a group from that dropdown while on the **Live** page now updates the
camera selector immediately without reloading the page, keeping navigation
seamless.

Searching the template grid automatically opens the camera detail view when
only one result matches, so you can jump straight to the live feed.

Template detail pages feature a back arrow in the header so you can quickly
return to the dashboard or group view without taking up extra page space.

Offline preview keeps recently viewed pages and assets in the browser cache so the interface remains responsive even on poor connections. This feature is enabled automatically.
