# MacRooster

MacRooster is a small macOS app that reads McDonald's roster emails, extracts your shifts, and adds them to Apple Calendar automatically.

## What It Does

- checks your mailbox for roster emails
- reads the attached PDF roster
- finds your shifts
- adds them to Apple Calendar
- avoids duplicate calendar events
- can re-add deleted future events when you check again

## Install For End Users

1. Open `MacRooster.dmg`
2. Drag `MacRooster.app` to `Applications`
3. Open `MacRooster` from `Applications`
4. Fill in your settings once

After that, MacRooster works in the background.

## Build A Release

```bash
./build_macrooster_release.sh
```

This creates:

- `release/MacRooster.dmg`
- `release/MacRooster Installatiegids.pdf`

## Files

- `macrooster_app.py`: main macOS app window
- `macrooster_setup.py`: first-run setup wizard
- `macrooster_core.py`: mail parsing, PDF parsing, Calendar logic
- `macrooster_notifier.swift`: native macOS notification helper
- `INSTALLATIEGIDS.md`: Dutch installation guide

## Notes

- this is macOS-only
- the app is not code signed or notarized yet
- because of that, macOS may show a security warning on first launch on other Macs
