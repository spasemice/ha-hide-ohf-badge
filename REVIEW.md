# Review of the original 1.0.0 app

Reviewed original commit: `43584a7818e614eb543e3efa0f54161c906c93f6`.

The repository already used the right outer structure: `repository.yaml` at
the root and an app folder with `config.yaml`. The runtime configuration and
the target being patched prevented it from working on the current installation.

| Original issue | Result | 1.1.0 change |
| --- | --- | --- |
| `image` points to an upstream base image and includes `:latest` | Supervisor uses a prebuilt image rather than building the custom Dockerfile; the app version is also treated as an image tag | Remove `image`, build the app Dockerfile from source |
| `boot: false` | Boot expects `auto`, `manual`, or `manual_only` | Use `boot: auto` |
| `startup: once` | Runs in the host startup sequence; does not subscribe to future Core updates | Start as a service, then block on Core start events |
| Script searches its own filesystem | Apps and Home Assistant Core have separate container filesystems | Use the Docker socket and exec in the fixed Core container ID |
| Script targets `ohf-badge.svg` | Current frontend uses `open-home-foundation-on-dark.svg` and `open-home-foundation-on-light.svg` | Locate `hass_frontend` dynamically and validate both targets |
| Backup is next to a file in an image/container | Originals are lost when that container is replaced | Save originals under Core's persistent `/config/branding-backups/automatic/` |
| `icon: icon.svg` | Not the supported app store icon mechanism | Supply square `icon.png` and `logo.png` in the app folder |

1.1.0 also supplies a read-only ingress status screen, removes SVG polling,
provides process-only watchdog health, and documents protection mode explicitly.

Validation: unit tests, actual aarch64 build/update on the Raspberry Pi,
verified Core SVG results, HTTP health, and authenticated ingress UI.
No Core upgrade/restart was performed as part of validation.

Official references:

- https://contributors.home-assistant.io/apps/reference/configuration/
- https://contributors.home-assistant.io/apps/reference/files/
- https://contributors.home-assistant.io/apps/guides/ingress/

The local installed app retains its original slug `blank_foundation_logo` for
upgrade continuity. The repository app retains `hide_ohf_badge` for existing
repository users. These are two installation sources; run only one at a time.
