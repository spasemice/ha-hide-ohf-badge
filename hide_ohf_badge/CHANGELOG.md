# 1.2.0

- Fix the browser preloader: patch gzip and Brotli copies that could still serve the original SVGs.
- Remove the complete Foundation footer from index.html while preserving the main logo and boot scripts.
- Patch the legacy badge when present, and back up all original files before writing.
- Detect cached Core launch HTML and report when a one-time Core restart is needed. Never restart Core automatically.
- Validate the fix with compressed-asset and launch-template tests and a copy of the actual installed frontend.

# 1.1.2

- Show a reference screenshot identifying the bottom Foundation badge in Info and the repository README.
- Explain that this is a personal appearance preference, with full support for Home Assistant and the Open Home Foundation.
- Correct the official Add repository badge and installer URL; include a plain text link.
- Refresh the installed app description with the updated wording.

# 1.1.1

- Add Back to app navigation from the status page to the app's Info tab.
- Use English throughout the status screen for international users.
- Explain automatic restoration after the next Core update when the app is disabled or uninstalled.
- Include app store icon and logo artwork.

# 1.1.0

- Remove the 300-second fallback timer. Check at app/Core startup or event-stream recovery only.
- Sleep on the Docker event stream between starts; no SVG polling.
- Add an authenticated, read-only status page with last result/time and Info settings.
- Enable Start on boot and Watchdog once on first 1.1.0 start, then respect user changes.
- Document Protection mode OFF in Info; no automatic security setting changes.
- Watchdog checks app responsiveness only, never SVG files.

# 1.0.0

- Initial release: blank both Foundation SVG logos, preserving originals.
