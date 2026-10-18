# Hide OHF Badge

Keeps both Foundation login/splash SVG logos blank after Core updates.

## Install or update

1. Open **Settings → Apps → Install app → Local apps → Hide OHF Badge**.
2. Select **Install**, or **Update** for an existing installation.
3. Set **Protection mode OFF**, **Start on boot ON**, and **Watchdog ON** in Info.
4. Select **Start**, then **Open Web UI** for the verified result and last check time.

Start on boot defaults to ON. On the first start of version 1.1 or later, the app also enables
Watchdog once using its own Supervisor self endpoint. Later changes to these
settings are respected. Protection mode must be disabled manually because it
grants Docker socket access; the manifest cannot make it the default.
Docker access is powerful. This app needs no Home Assistant credentials and
does not request the Supervisor manager/admin role.

## Startup checks and sleep

The app subscribes to Core container start events, checks once after connecting,
then blocks waiting for another Core start. There is no timer and no periodic
SVG check. A Core update replaces/restarts the container, triggering a new check.
Only a disconnected event stream causes a reconnect attempt (10-second backoff)
and a recovery check, so an event lost during Docker downtime is covered.

The process stays in memory while sleeping so it can receive the next start
event. It also answers on-demand status requests through authenticated Home
Assistant ingress. No port is exposed to the LAN. Watchdog health requests only
check the listener thread, never execute Python in Core or read the SVG files.

## Status and configuration

**Open Web UI** shows success/error, last verified time, Core image, number of
checks since the app started, listener state, and actual Info settings. Refresh
is manual: the page does not poll. A result is saved in the app's data directory
as status.json only when a real check occurs. Logs record success and errors.

The native Configuration tab has no options because there is no interval to
configure. Home Assistant does not support a live read-only result field in its
options form; status and settings feedback is in **Open Web UI** instead.

Originals are saved under the Home Assistant configuration folder:
branding-backups/automatic/<content-hash>/<original-filename>.
Already-blank files are not rewritten. Missing or unexpected SVGs cause an
error rather than a change to unrelated files. A cached logo may require a
browser hard refresh after patching.

## Stop or uninstall

Select Stop and turn off Start on boot. Uninstall from the same app page.
Stopping does not restore originals; use the saved backups or a Core update.

## Another Home Assistant

Copy this folder into the Supervisor local apps directory, then refresh the app
store. Supports aarch64 and amd64 with Home Assistant OS or Supervisor.

## Restore default logos

To restore the default Home Assistant logos, stop this app and disable
**Start on boot**, or uninstall the app. The next **Home Assistant Core update**
will automatically restore the original logos. Stopping or uninstalling the app
does not restore the logos immediately.
