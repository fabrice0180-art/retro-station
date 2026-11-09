#!/bin/bash
# Fabrique « Rétro Station.app » et son DMG. Usage : build_dmg.sh Intel|AppleSilicon
set -euo pipefail
LABEL="${1:?Intel ou AppleSilicon}"
VERSION="${RS_VERSION:-$(python3 -c 'import sys; sys.path.insert(0, "."); from retrostation import paths; print(paths.VERSION)')}"

pyinstaller --noconfirm --windowed --name "Retro Station" \
  --icon assets/icon.icns --add-data "assets:assets" \
  --osx-bundle-identifier fr.fabricem.retrostation RetroStation.pyw

APP="dist/Retro Station.app"
PL="$APP/Contents/Info.plist"
set_key() { /usr/libexec/PlistBuddy -c "Set :$1 $3" "$PL" 2>/dev/null || /usr/libexec/PlistBuddy -c "Add :$1 $2 $3" "$PL"; }
set_key CFBundleName string "Rétro Station"
set_key CFBundleDisplayName string "Rétro Station"
set_key CFBundleShortVersionString string "$VERSION"
set_key CFBundleVersion string "$VERSION"
set_key NSHumanReadableCopyright string "Fabrice M."
set_key NSHighResolutionCapable bool true
set_key LSApplicationCategoryType string "public.app-category.games"
# signature locale (obligatoire sur puce M)
codesign --force --deep --sign - "$APP"

rm -rf dmg && mkdir -p dmg installers
cp -R "$APP" "dmg/Rétro Station.app"
ln -s /Applications dmg/Applications
OUT="installers/RetroStation-$VERSION-Mac-$LABEL.dmg"
hdiutil create -volname "Rétro Station" -srcfolder dmg -ov -format UDZO "$OUT"
echo "DMG : $OUT"
