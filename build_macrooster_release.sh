#!/usr/bin/env bash
set -euo pipefail

APP_NAME="MacRooster"
VOL_NAME="MacRooster"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$ROOT_DIR/dist"
BUILD_DIR="$ROOT_DIR/build"
RELEASE_DIR="$ROOT_DIR/release"
DMG_STAGING_DIR="$RELEASE_DIR/dmg"
DMG_PATH="$RELEASE_DIR/${APP_NAME}.dmg"
GUIDE_SOURCE="$ROOT_DIR/INSTALLATIEGIDS.md"
GUIDE_PDF_PATH="$RELEASE_DIR/MacRooster Installatiegids.pdf"
SPEC_PATH="$ROOT_DIR/${APP_NAME}.spec"
ICON_SOURCE="$ROOT_DIR/assets/macrooster-logo.png"
ICONSET_DIR="$RELEASE_DIR/${APP_NAME}.iconset"
ICNS_PATH="$RELEASE_DIR/${APP_NAME}.icns"
NOTIFIER_APP_NAME="MacRoosterNotifier"
NOTIFIER_BUNDLE="$RELEASE_DIR/${NOTIFIER_APP_NAME}.app"
NOTIFIER_BINARY="$NOTIFIER_BUNDLE/Contents/MacOS/${NOTIFIER_APP_NAME}"
NOTIFIER_PLIST="$NOTIFIER_BUNDLE/Contents/Info.plist"
NOTIFIER_ICON="$NOTIFIER_BUNDLE/Contents/Resources/AppIcon.icns"
PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYINSTALLER_CONFIG_DIR="$ROOT_DIR/.pyinstaller"

echo "1. Oude build opruimen…"
rm -rf "$DIST_DIR" "$BUILD_DIR" "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

echo "2. App-icoon maken…"
mkdir -p "$ICONSET_DIR"
sips -z 16 16 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null
sips -z 32 32 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null
sips -z 32 32 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null
sips -z 64 64 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null
sips -z 128 128 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null
sips -z 256 256 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null
sips -z 256 256 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null
sips -z 512 512 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null
sips -z 512 512 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null
sips -z 1024 1024 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null
iconutil -c icns "$ICONSET_DIR" -o "$ICNS_PATH"

echo "3. Notificatie-helper bouwen…"
mkdir -p "$NOTIFIER_BUNDLE/Contents/MacOS" "$NOTIFIER_BUNDLE/Contents/Resources"
/usr/bin/swiftc \
  -O \
  -parse-as-library \
  -o "$NOTIFIER_BINARY" \
  "$ROOT_DIR/macrooster_notifier.swift"
cp "$ICNS_PATH" "$NOTIFIER_ICON"
cat > "$NOTIFIER_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key>
  <string>MacRooster</string>
  <key>CFBundleExecutable</key>
  <string>${NOTIFIER_APP_NAME}</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundleIdentifier</key>
  <string>com.macrooster.notifier</string>
  <key>CFBundleName</key>
  <string>MacRooster</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
</dict>
</plist>
EOF

echo "4. macOS app bouwen…"
"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --windowed \
  --onedir \
  --name "$APP_NAME" \
  --icon "$ICNS_PATH" \
  --osx-bundle-identifier "com.macrooster.app" \
  --add-data "$ROOT_DIR/assets:assets" \
  --add-data "$ROOT_DIR/macrooster_app.py:." \
  --add-data "$ROOT_DIR/macrooster_core.py:." \
  --add-data "$ROOT_DIR/macrooster_setup.py:." \
  --collect-all pdfplumber \
  --collect-all pdfminer \
  --collect-all pypdfium2 \
  "$ROOT_DIR/macrooster_app.py"

APP_PATH="$DIST_DIR/$APP_NAME.app"
if [ ! -d "$APP_PATH" ]; then
  echo "Build mislukt: $APP_PATH niet gevonden"
  exit 1
fi

cp -R "$NOTIFIER_BUNDLE" "$APP_PATH/Contents/Resources/"

echo "5. DMG-map voorbereiden…"
mkdir -p "$DMG_STAGING_DIR"
cp -R "$APP_PATH" "$DMG_STAGING_DIR/"
ln -s /Applications "$DMG_STAGING_DIR/Applications"

echo "6. DMG maken…"
hdiutil create \
  -volname "$VOL_NAME" \
  -srcfolder "$DMG_STAGING_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

if command -v pandoc >/dev/null 2>&1 && [ -f "$GUIDE_SOURCE" ]; then
  echo "7. Installatiegids naar PDF omzetten…"
  pandoc "$GUIDE_SOURCE" \
    --metadata title="MacRooster Installatiegids" \
    -o "$GUIDE_PDF_PATH"
else
  echo "7. Installatiegids PDF overgeslagen (pandoc of INSTALLATIEGIDS.md ontbreekt)."
fi

echo ""
echo "Klaar."
echo "App : $APP_PATH"
echo "DMG : $DMG_PATH"
if [ -f "$GUIDE_PDF_PATH" ]; then
  echo "PDF : $GUIDE_PDF_PATH"
fi

rm -rf "$BUILD_DIR" "$DIST_DIR" "$DMG_STAGING_DIR" "$PYINSTALLER_CONFIG_DIR" "$ICONSET_DIR" "$NOTIFIER_BUNDLE"
rm -f "$SPEC_PATH" "$ICNS_PATH"
