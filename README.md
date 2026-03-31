# MacRooster

MacRooster is a small macOS app that reads McDonald's roster emails, extracts your shifts from the attached PDF, and adds them to Apple Calendar automatically.

It is built for people who just want their new work hours to show up in Agenda without copying them manually.

## Highlights

- macOS app with drag-to-Applications install flow
- setup wizard for mailbox and calendar settings
- reads roster PDFs from email automatically
- adds shifts to Apple Calendar
- avoids duplicate calendar events
- can restore deleted future events when you check again
- optional macOS notification when new shifts are added

## Installation

1. Open `MacRooster.dmg`
2. Drag `MacRooster.app` to `Applications`
3. Open `MacRooster` from `Applications`
4. Fill in your settings once

After that, MacRooster works in the background.

For the Dutch install guide, see [INSTALLATIEGIDS.md](INSTALLATIEGIDS.md).

## How It Works

1. MacRooster connects to your mailbox through IMAP
2. It looks for roster emails from McDonald's
3. It extracts text from the attached PDF roster
4. It finds the shifts that belong to your name
5. It writes those shifts into Apple Calendar

## Project Structure

- `macrooster_app.py`: main macOS app window
- `macrooster_setup.py`: first-run setup wizard
- `macrooster_core.py`: email parsing, PDF parsing, Calendar logic
- `macrooster_notifier.swift`: native macOS notification helper
- `build_macrooster_release.sh`: release builder for DMG and PDF guide
- `INSTALLATIEGIDS.md`: Dutch installation guide

## Build A Release

```bash
./build_macrooster_release.sh
```

This creates:

- `release/MacRooster.dmg`
- `release/MacRooster Installatiegids.pdf`

## Notes

- macOS only
- not affiliated with McDonald's
- not code signed or notarized yet
- because of that, macOS may show a security warning on first launch on other Macs

## License

[MIT](LICENSE)
