#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export CAPACITOR_ANDROID_STUDIO_PATH="$HOME/android-studio/bin/studio.sh"

usage() {
  cat <<EOF
Praina Capacitor helper

Usage:
  ./cap.sh dev           Sync with dev server (http://localhost:5173)
  ./cap.sh prod          Sync with production (https://c3lab.poliba.it/praina)
  ./cap.sh build         Build frontend, then sync for production
  ./cap.sh run [android] Run on device/emulator (default: android)
  ./cap.sh icons         Generate Android app icons from the Praina logo SVG
  ./cap.sh open          Open the Android project in Android Studio
  ./cap.sh help          Show this message
EOF
}

sync_dev() {
  echo "==> Syncing for development (localhost:5173)..."
  CAPACITOR_ENV=dev npx cap sync
  echo "Done. Run './cap.sh run' to launch on device."
}

sync_prod() {
  echo "==> Syncing for production (c3lab.poliba.it/praina)..."
  npx cap sync
  echo "Done."
}

build_and_sync() {
  echo "==> Building frontend..."
  npx vite build
  echo "==> Syncing for production..."
  npx cap sync
  echo "Done."
}

run_app() {
  local platform="${1:-android}"
  echo "==> Running on $platform..."
  npx cap run "$platform"
}

generate_icons() {
  local SVG="src/assets/praina-logo-black.svg"
  if [ ! -f "$SVG" ]; then
    echo "Error: $SVG not found"
    exit 1
  fi

  if ! command -v inkscape &>/dev/null; then
    echo "Error: inkscape is required for icon generation"
    exit 1
  fi

  local RES_DIR="android/app/src/main/res"

  # Android mipmap sizes: mdpi=48, hdpi=72, xhdpi=96, xxhdpi=144, xxxhdpi=192
  # Foreground (adaptive icon): mdpi=108, hdpi=162, xhdpi=216, xxhdpi=324, xxxhdpi=432
  declare -A ICON_SIZES=(
    [mdpi]=48
    [hdpi]=72
    [xhdpi]=96
    [xxhdpi]=144
    [xxxhdpi]=192
  )
  declare -A FG_SIZES=(
    [mdpi]=108
    [hdpi]=162
    [xhdpi]=216
    [xxhdpi]=324
    [xxxhdpi]=432
  )

  TMPDIR="$(mktemp -d)"
  trap 'rm -rf "$TMPDIR"' EXIT

  echo "==> Generating app icons from $SVG..."

  for density in mdpi hdpi xhdpi xxhdpi xxxhdpi; do
    local size="${ICON_SIZES[$density]}"
    local fg_size="${FG_SIZES[$density]}"
    local mipmap_dir="$RES_DIR/mipmap-${density}"
    mkdir -p "$mipmap_dir"

    # Launcher icon: white logo on dark teal background
    local bg_png="$TMPDIR/bg_${density}.png"
    local logo_png="$TMPDIR/logo_${density}.png"

    # Create background
    convert -size "${size}x${size}" "xc:#101012" -fill "#18181C" \
      -draw "roundrectangle 0,0 $((size-1)),$((size-1)) $((size/8)),$((size/8))" \
      "$bg_png"

    # Render logo (80% of icon size, centered)
    local logo_size=$((size * 70 / 100))
    inkscape "$SVG" --export-type=png --export-filename="$logo_png" \
      -w "$logo_size" -h "$logo_size" 2>/dev/null

    # Composite logo on background
    convert "$bg_png" "$logo_png" -gravity center -composite "$mipmap_dir/ic_launcher.png"
    # Round version
    convert "$mipmap_dir/ic_launcher.png" \
      \( +clone -threshold -1 -negate -fill white -draw "circle $((size/2)),$((size/2)) $((size/2)),0" \) \
      -alpha off -compose copy_opacity -composite "$mipmap_dir/ic_launcher_round.png"

    # Foreground for adaptive icons (logo only, transparent bg, centered in larger canvas)
    local fg_logo_size=$((fg_size * 50 / 100))
    local fg_logo_png="$TMPDIR/fg_logo_${density}.png"
    inkscape "$SVG" --export-type=png --export-filename="$fg_logo_png" \
      -w "$fg_logo_size" -h "$fg_logo_size" 2>/dev/null
    convert -size "${fg_size}x${fg_size}" "xc:transparent" \
      "$fg_logo_png" -gravity center -composite "$mipmap_dir/ic_launcher_foreground.png"

    echo "    $density: ${size}px icon, ${fg_size}px foreground"
  done

  echo "Done. Icons written to $RES_DIR/mipmap-*/"
}

open_studio() {
  echo "==> Opening Android project..."
  npx cap open android
}

case "${1:-help}" in
  dev)    sync_dev ;;
  prod)   sync_prod ;;
  build)  build_and_sync ;;
  run)    run_app "${2:-android}" ;;
  icons)  generate_icons ;;
  open)   open_studio ;;
  help|*) usage ;;
esac
