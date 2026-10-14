# Luma for macOS

A little more time. Keep your Mac awake with a quiet timer and a live halo in the menu bar.

**Preview release — Apple silicon, macOS 13 or later.** These preview builds are not yet Developer ID signed or notarized. macOS may block their first launch. They are intended for testing; do not disable your Mac's security settings.

[Download the latest installer](https://github.com/roeyj/luma-releases/releases/latest/download/Luma.dmg) · [All downloads and release notes](https://github.com/roeyj/luma-releases/releases)

Open the disk image, drag Luma into Applications, then open it from Applications. Enabling the timer service on a new Mac requires one administrator approval. Routine timer starts and stops then use the existing approved service.

## Updates

Starting with version 2.3, Luma checks for updates daily, verifies their signatures, and downloads them in the background. You can check manually or change automatic-update preferences in the Luma menu. An active timer continues when the app closes for an update.

Updates preserve the approved timer connection. This preview track still uses the original local bridge. A future transition to an Apple-signed distribution may need a separate, explicit one-time service migration; it will not be silently performed by a routine UI update.

The feed and update archives are signed with a dedicated Ed25519 key. Signing keys and application source are not included in this repository. This repository holds release downloads and the disk-image packaging recipe only.

Luma uses [Sparkle](https://sparkle-project.org/) for updates. Its license is included inside the app.
