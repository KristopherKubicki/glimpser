#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build/ffmpeg"
BIN_DIR="$ROOT_DIR/bin"

FFMPEG_VERSION="6.1"

mkdir -p "$BUILD_DIR" "$BIN_DIR"
cd "$BUILD_DIR"

if [ ! -d "ffmpeg-$FFMPEG_VERSION" ]; then
  curl -L -o ffmpeg.tar.gz "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.gz"
  tar xf ffmpeg.tar.gz
fi
cd "ffmpeg-$FFMPEG_VERSION"

./configure \
  --prefix="$BUILD_DIR/install" \
  --enable-gpl --enable-nonfree \
  --enable-nvenc --enable-cuda-nvcc --enable-libnpp \
  --enable-vaapi --enable-libdrm

make -j"$(nproc)"
make install

cp "$BUILD_DIR/install/bin/ffmpeg" "$BIN_DIR/ffmpeg"
cp "$BUILD_DIR/install/bin/ffprobe" "$BIN_DIR/ffprobe"

