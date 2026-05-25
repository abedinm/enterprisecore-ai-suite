# Release process

EnterpriseCore AI Suite ships from a tag-driven pipeline. Every `v*` tag
pushed to `main` triggers `.github/workflows/release.yml`, which builds the
installers for Windows, macOS, and Linux in parallel, generates a CycloneDX
SBOM, optionally signs/notarizes, and publishes a GitHub Release with all
artifacts attached.

## Channels

| Channel | Tag pattern    | Audience           |
|---------|----------------|--------------------|
| latest  | `v1.2.3`       | Production users   |
| beta    | `v1.2.3-beta.1`| Early-adopter ring |
| rc      | `v1.2.3-rc.1`  | Internal QA        |

`electron-updater` reads the channel from the tag suffix automatically.
`-beta` and `-rc` tags publish as **prereleases** on GitHub and feed the
matching auto-update channel.

## Cutting a release

1. **Confirm `main` is green.** All CI checks must pass on the commit you
   intend to tag.

2. **Bump the version** in three places so they stay in sync:
   - `backend/app/__init__.py` → `__version__ = "0.6.0"`
   - `frontend/package.json` → `"version": "0.6.0"`
   - `electron/package.json` → `"version": "0.6.0"`

   For a beta or rc, suffix accordingly: `0.6.0-beta.1`.

3. **Update the changelog.** Add the new version section to
   `docs/CHANGELOG.md` (or create one if it does not yet exist) with a
   bulleted list of user-facing changes.

4. **Commit and push** with a `chore(release): vX.Y.Z` message.

   ```bash
   git add backend/app/__init__.py frontend/package.json electron/package.json \
           docs/CHANGELOG.md
   git commit -m "chore(release): v0.6.0"
   git push origin main
   ```

5. **Tag and push the tag.**

   ```bash
   git tag -a v0.6.0 -m "v0.6.0"
   git push origin v0.6.0
   ```

6. **Watch the pipeline.** `release.yml` runs on three runners in parallel
   (Ubuntu, Windows, macOS). Each one:
   - Installs Python 3.13 + Node 20
   - Builds the backend via PyInstaller (`backend/enterprisecore-backend.spec`)
   - Builds the frontend (`npm run build`)
   - Stages backend resources into `electron/resources/backend`
   - Runs `electron-builder` with the platform-appropriate flags
   - Generates a CycloneDX SBOM via `anchore/sbom-action`
   - Uploads installers as artifacts

   Once all three runners finish, a final `release` job downloads every
   artifact and publishes a single GitHub Release with the binaries
   attached.

7. **Smoke-test the installers** before announcing. For each platform:
   - Install on a clean VM
   - Launch, sign in with the seeded admin account
   - Confirm backend starts on its bundled port
   - Confirm frontend loads and at least one module renders
   - Confirm auto-update check fires (Help -> Check for updates)

8. **Announce.** Drop the release link in the release channel.

## Signing and notarization

These steps only run when the corresponding secrets are configured in the
GitHub repo settings. Missing secrets are not an error — the build will
just produce unsigned binaries.

### Windows code signing

Set these secrets:

- `WINDOWS_CERT` — base64-encoded `.pfx` certificate
- `WINDOWS_CERT_PASSWORD` — the certificate password

The workflow decodes the cert into a tmp file and points
`electron-builder` at it via `CSC_LINK` + `CSC_KEY_PASSWORD`.

### macOS signing + notarization

Set these secrets:

- `MAC_CERT` — base64-encoded Developer ID `.p12`
- `MAC_CERT_PASSWORD` — the cert password
- `APPLE_ID` — Apple ID email
- `APPLE_PASSWORD` — app-specific password (not your Apple ID password)
- `APPLE_TEAM_ID` — 10-character team ID from Apple Developer portal

The workflow forwards these as env vars to `electron-builder`, which signs
with the cert and submits to Apple's notary service.

## Rolling back a bad release

A release that ships a regression needs three things rolled back: the tag,
the GitHub Release, and a revert PR on `main`.

1. **Delete the GitHub Release** in the web UI (the artifacts go with it).
   This also stops the auto-updater from offering it.

2. **Delete the local and remote tag.**

   ```bash
   git tag -d v0.6.0
   git push origin :refs/tags/v0.6.0
   ```

3. **Revert the release commit on `main`** via a normal PR. Do not
   force-push — open a revert PR, get a review, merge.

   ```bash
   git revert <release-commit-sha>
   ```

4. **Cut the next patch.** Bump to `v0.6.1`, fix the regression, and ship
   normally. Users on `0.6.0` will pick up `0.6.1` from the updater feed.

## Auto-update feed

`electron-updater` reads release metadata from:

```
https://updates.enterprisecore.local/${channel}
```

This is configured under `build.publish` in `electron/package.json`. To
host the feed somewhere else, update that URL and re-tag.

GitHub Release assets include the `latest.yml`, `latest-mac.yml`, and
`latest-linux.yml` files that the updater reads. The release pipeline
generates these automatically via `generateUpdatesFilesForAllChannels`.
