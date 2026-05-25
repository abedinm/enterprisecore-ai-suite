# Auto-update — EnterpriseCore AI Suite

The Electron desktop app ships with `electron-updater` wired into the main
process. New releases are detected, downloaded, and applied without the user
having to re-run an installer.

## How it works

1. **Startup check.** Roughly one second after the main window opens, the app
   asks the update server for the latest release on the active channel.
2. **Periodic check.** A timer re-checks every **4 hours** while the app is
   running. Cheap (a single HEAD/GET request) and silent on failure.
3. **Prompt to download.** If a newer version exists, the user sees a native
   dialog with *Download* / *Skip*. Auto-download is off so we never burn the
   user's bandwidth without consent.
4. **Background download.** When the user accepts, the binary downloads in the
   background. The app stays usable throughout.
5. **Prompt to install.** Once the download finishes a second dialog offers
   *Restart now* / *Later*. *Later* defers the install to the next app quit
   (`autoInstallOnAppQuit = true`).

If the update server is unreachable (DNS, 404, network down) the failure is
swallowed — no UI errors are shown.

## Update URL convention

The publish config in `electron/package.json` uses the generic provider:

```
https://updates.enterprisecore.local/${channel}
```

`${channel}` is interpolated by `electron-builder` at publish time. Supported
channels:

| Channel  | Audience           | URL                                       |
| -------- | ------------------ | ----------------------------------------- |
| `latest` | All users          | `https://updates.enterprisecore.local/latest` |
| `beta`   | Opt-in pre-release | `https://updates.enterprisecore.local/beta`   |

Change to GitHub Releases or S3 by editing `electron/package.json` -> `build.publish`.
See <https://www.electron.build/configuration/publish>.

## Self-hosting an update server

Minimum: serve a single directory over HTTPS with two files per channel.

```
https://updates.enterprisecore.local/latest/
  latest.yml                          # manifest (electron-builder generates this)
  EnterpriseCore AI Suite-Setup-X.Y.Z-x64.exe
  EnterpriseCore AI Suite-Setup-X.Y.Z-x64.exe.blockmap
```

Any static host works (nginx, S3+CloudFront, Caddy, GitHub Pages). The
`*.blockmap` file enables delta updates — keep it next to the installer.

Publishing flow:

```
cd electron
npm run dist:win
# Upload electron/dist/latest.yml + the .exe + .exe.blockmap to the channel directory.
```

## Manual trigger

The renderer can invoke `app:check-for-updates` via IPC to force a check now,
e.g. from a Help -> "Check for updates" menu item. The handler returns
`{ status, updateAvailable, version }` or `{ status: 'error', error }`.

## Channel selection

Beta builds: set the environment variable before launching the installed app.

```
setx EC_UPDATE_CHANNEL beta
```

The app will start polling the `/beta` channel and accept prereleases
(`allowPrerelease = true`).

## Disabling

To turn auto-update off entirely (air-gapped installs, locked-down kiosks):

```
setx EC_UPDATE_CHANNEL disabled
```

The `setupAutoUpdater()` function exits early and the `app:check-for-updates`
IPC handler returns `{ status: 'skipped', reason: 'disabled' }`.

Dev builds (`ELECTRON_DEV=1`) skip the updater automatically — running
`npm run dev` will never hit a real release server.

## Operational notes

- Builds must be signed for `electron-updater` to verify them on Windows. The
  current CI does not sign yet; once signing is in place set
  `verifyUpdateCodeSignature: true` (default) is enough.
- Versioning follows semver. `electron-updater` only prompts when the remote
  version is **strictly greater** than the installed one — equal or older
  versions are ignored.
- Logs from the updater are routed to `console`, which the main process pipes
  into `electron/app-stdout.log` / `app-stderr.log`.
