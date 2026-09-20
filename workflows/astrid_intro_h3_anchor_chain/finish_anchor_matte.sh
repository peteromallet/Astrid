#!/bin/zsh
# Finish a native H3 continuation as flat orange pixel art on black.
#
# Usage:
#   finish_anchor_matte.sh SOURCE START_ANCHOR END_ANCHOR OUTPUT.mp4 \
#       [FRAMES=260] [PROTECTED_PREFIX=39] [FADE_START=120] [FADE_END=168] \
#       [HEAD_HEIGHT=350] [FPS=24] [WIDTH=1920] [HEIGHT=1088]
set -euo pipefail

if (( $# < 4 )); then
  print -u2 "usage: $0 SOURCE START_ANCHOR END_ANCHOR OUTPUT.mp4 [frames] [prefix] [fade_start] [fade_end] [head_height] [fps] [width] [height]"
  exit 2
fi

SRC=$1
START_ANCHOR=$2
END_ANCHOR=$3
FINAL=$4
FRAMES=${5:-260}
PREFIX=${6:-39}
FADE_START=${7:-120}
FADE_END=${8:-168}
HEAD_HEIGHT=${9:-350}
FPS=${10:-24}
WIDTH=${11:-1920}
HEIGHT=${12:-1088}
OUT_DIR=$(dirname "$FINAL")
mkdir -p "$OUT_DIR"
DURATION=$(awk -v n="$FRAMES" -v fps="$FPS" 'BEGIN { printf "%.6f", n / fps }')
HEAD="${FINAL%.mp4}.head.mp4"
CONTACT="${FINAL%.mp4}_contact.png"

# The heading stream is a real finite video, avoiding framesync holding the
# first anchor. It holds the start anchor, crossfades, then holds the end.
ffmpeg -y -hide_banner -loglevel error \
  -loop 1 -i "$START_ANCHOR" -loop 1 -i "$END_ANCHOR" \
  -filter_complex "[0:v]fps=$FPS,trim=duration=$DURATION,setpts=N/($FPS*TB),crop=iw:$HEAD_HEIGHT:0:0[h4];[1:v]fps=$FPS,trim=duration=$DURATION,setpts=N/($FPS*TB),crop=iw:$HEAD_HEIGHT:0:0[h5];[h4][h5]blend=all_expr='if(lt(N\\,$FADE_START)\\,A\\,if(gt(N\\,$FADE_END)\\,B\\,A*(1-(N-$FADE_START)/($FADE_END-$FADE_START))+B*((N-$FADE_START)/($FADE_END-$FADE_START))))'" \
  -frames:v "$FRAMES" -t "$DURATION" -r "$FPS" -c:v libx264 -preset fast -crf 16 -pix_fmt yuv420p -an "$HEAD"

# Preserve the native prefix content (it is reencoded in the final MP4), then
# matte only the new frames. Heading and body are composited on one canvas.
ffmpeg -y -hide_banner -loglevel error -i "$SRC" -i "$HEAD" \
  -filter_complex "[0:v]split=2[orig][proc];[proc]crop=iw:ih-$HEAD_HEIGHT:0:$HEAD_HEIGHT,chromakey=0x808080:0.18:0.0,format=rgba[fg];color=c=black:s=${WIDTH}x$((HEIGHT-HEAD_HEIGHT)):r=$FPS:d=${DURATION}[blk];[blk][fg]overlay=format=rgb:eof_action=repeat:shortest=1[body];color=c=black:s=${WIDTH}x${HEIGHT}:r=$FPS:d=${DURATION}[canvas];[canvas][body]overlay=x=0:y=$HEAD_HEIGHT:format=rgb:eof_action=repeat:shortest=1[canvasbody];[1:v]setpts=PTS-STARTPTS[head];[canvasbody][head]overlay=x=0:y=0:format=yuv420:eof_action=repeat:shortest=1[cleanfull];[orig]trim=end_frame=$PREFIX,setpts=N/($FPS*TB)[prefix];[cleanfull]trim=start_frame=$PREFIX,setpts=N/($FPS*TB)[tail];[prefix][tail]concat=n=2:v=1:a=0,format=yuv420p,setpts=N/($FPS*TB)[out]" \
  -map '[out]' -frames:v "$FRAMES" -t "$DURATION" -r "$FPS" \
  -c:v libx264 -preset fast -crf 16 -pix_fmt yuv420p -an -movflags +faststart "$FINAL"

S1=$(( (FRAMES - 1) / 7 )); S2=$(( 2 * (FRAMES - 1) / 7 )); S3=$(( 3 * (FRAMES - 1) / 7 ))
S4=$(( 4 * (FRAMES - 1) / 7 )); S5=$(( 5 * (FRAMES - 1) / 7 )); S6=$(( 6 * (FRAMES - 1) / 7 ))
SELECT="eq(n\\,0)+eq(n\\,$S1)+eq(n\\,$S2)+eq(n\\,$S3)+eq(n\\,$S4)+eq(n\\,$S5)+eq(n\\,$S6)+eq(n\\,$((FRAMES-1)))"
ffmpeg -y -nostdin -v error -i "$FINAL" \
  -vf "drawtext=fontcolor=white:fontsize=70:box=1:boxcolor=black@0.75:text='anchor matte source=%{n}',select='$SELECT',setpts=N/($FPS*TB),scale=480:-2:flags=neighbor,tile=4x2" \
  -frames:v 1 "$CONTACT"

ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames,r_frame_rate,duration,width,height -of default=nw=1 "$FINAL"
