#!/bin/zsh
# Reproducible finishing for accepted full-frame H3 matte passes.
#
# Full-frame terminal pass (s04):
#   finish_fullframe_matte.sh fullframe SOURCE OUTPUT.mp4 [frames] [fps] [width] [height]
#
# Full-frame pass with a managed v05 header that holds then fades away (s03):
#   finish_fullframe_matte.sh headerfade SOURCE HEADER_IMAGE OUTPUT.mp4 \
#       [frames] [fade_start_frame] [fade_end_frame] [fps] [width] [height]
#
# All outputs are silent, finite 24-fps H.264 renders. The headerfade mode
# replaces only the top HEAD_HEIGHT pixels while its anchor remains opaque;
# after fade_end_frame the full-frame matte is left intact so rising subjects
# cannot be cropped by a permanent top strip.
set -euo pipefail

if (( $# < 3 )); then
  print -u2 "usage: $0 fullframe SOURCE OUTPUT.mp4 [frames] [fps] [width] [height]"
  print -u2 "   or: $0 headerfade SOURCE HEADER_IMAGE OUTPUT.mp4 [frames] [fade_start] [fade_end] [fps] [width] [height]"
  exit 2
fi

MODE=$1
SRC=$2
if [[ "$MODE" == fullframe ]]; then
  FINAL=$3
  FRAMES=${4:-175}; FPS=${5:-24}; WIDTH=${6:-1920}; HEIGHT=${7:-1088}
  HEAD_HEIGHT=0
  FADE_START=0; FADE_END=0
elif [[ "$MODE" == headerfade ]]; then
  if (( $# < 4 )); then exit 2; fi
  HEADER=$3; FINAL=$4
  FRAMES=${5:-175}; FADE_START=${6:-70}; FADE_END=${7:-125}
  FPS=${8:-24}; WIDTH=${9:-1920}; HEIGHT=${10:-1088}
  HEAD_HEIGHT=${11:-350}
else
  print -u2 "mode must be fullframe or headerfade"; exit 2
fi

if (( FADE_END < FADE_START )); then
  print -u2 "fade_end must be >= fade_start"; exit 2
fi
OUT_DIR=$(dirname "$FINAL"); mkdir -p "$OUT_DIR"
DURATION=$(awk -v n="$FRAMES" -v fps="$FPS" 'BEGIN { printf "%.6f", n / fps }')

if [[ "$MODE" == fullframe ]]; then
  ffmpeg -y -nostdin -hide_banner -loglevel error -i "$SRC" \
    -filter_complex "[0:v]chromakey=0x808080:0.18:0.0,format=rgba[fg];color=c=black:s=${WIDTH}x${HEIGHT}:r=$FPS:d=${DURATION}[blk];[blk][fg]overlay=format=rgb:eof_action=repeat:shortest=1,format=yuv420p,setpts=N/($FPS*TB)[out]" \
    -map '[out]' -frames:v "$FRAMES" -t "$DURATION" -r "$FPS" \
    -c:v libx264 -preset fast -crf 16 -pix_fmt yuv420p -an -movflags +faststart "$FINAL"
else
  FADE_DURATION=$(awk -v a="$FADE_START" -v b="$FADE_END" -v fps="$FPS" 'BEGIN { printf "%.6f", (b-a)/fps }')
  FADE_TIME=$(awk -v a="$FADE_START" -v fps="$FPS" 'BEGIN { printf "%.6f", a/fps }')
  # The looped anchor is trimmed to the finite output duration. Alpha fade
  # exposes the full-frame matte beneath it after the requested end frame.
  ffmpeg -y -nostdin -hide_banner -loglevel error -i "$SRC" -loop 1 -i "$HEADER" \
    -filter_complex "[0:v]chromakey=0x808080:0.18:0.0,format=rgba[fg];color=c=black:s=${WIDTH}x${HEIGHT}:r=$FPS:d=${DURATION}[blk];[blk][fg]overlay=format=rgb:eof_action=repeat:shortest=1[body];[1:v]fps=$FPS,trim=duration=${DURATION},setpts=N/($FPS*TB),crop=iw:$HEAD_HEIGHT:0:0,format=rgba,fade=t=out:st=${FADE_TIME}:d=${FADE_DURATION}:alpha=1[head];[body][head]overlay=x=0:y=0:format=rgb:eof_action=repeat:shortest=1,format=yuv420p,setpts=N/($FPS*TB)[out]" \
    -map '[out]' -frames:v "$FRAMES" -t "$DURATION" -r "$FPS" \
    -c:v libx264 -preset fast -crf 16 -pix_fmt yuv420p -an -movflags +faststart "$FINAL"
fi

ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames,r_frame_rate,duration,width,height -of default=nw=1 "$FINAL"
