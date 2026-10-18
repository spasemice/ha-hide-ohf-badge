# Hide OHF Badge

Checks and blanks both Foundation login/splash logos when Home Assistant Core
starts, then sleeps waiting for the next Core start event. No periodic SVG
checks, no 300-second timer, and no automatic Home Assistant restart.

**Required Info settings:**

| Setting | Value |
| --- | --- |
| Start on boot | **ON** (default) |
| Watchdog | **ON** (enabled once on the first start of version 1.1 or later) |
| Protection mode | **OFF** (set manually before Start) |

Select **Open Web UI** for the last verified result, check time, sleeping state,
and current Info settings. The standard Configuration tab has no options.
Watchdog checks only that this app is responsive; it never checks the SVG files.

Protection mode is a Supervisor security setting and cannot be disabled by the
app manifest. This app does not grant itself an admin role or turn off protection.
Docker access is needed to replace the two files inside Core.

## Restore default logos

To restore the default Home Assistant logos, stop this app and disable
**Start on boot**, or uninstall the app. The next **Home Assistant Core update**
will automatically restore the original logos. Stopping or uninstalling the app
does not restore the logos immediately.
