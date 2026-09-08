import type {ReactElement} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';

export type ReviewContext = {
  shots: Array<{shot_id: string; name: string; at: number; hold: number}>;
};

export const reviewLabel = (review: ReviewContext, frame: number, fps: number): string => {
  const time = frame / fps;
  const names = review.shots.filter(shot => time >= shot.at && time < shot.at + shot.hold).map(shot => shot.name);
  const milliseconds = Math.floor(time * 1000);
  const hours = Math.floor(milliseconds / 3600000);
  const minutes = Math.floor(milliseconds / 60000) % 60;
  const seconds = Math.floor(milliseconds / 1000) % 60;
  const clock = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(milliseconds % 1000).padStart(3, '0')}`;
  return `${names.join(' / ') || 'No shot'}  ·  ${clock}`;
};

export const ReviewOverlay = ({review}: {review?: ReviewContext | null}): ReactElement | null => {
  const frame = useCurrentFrame();
  const {fps, width} = useVideoConfig();
  if (!review) return null;
  return <AbsoluteFill style={{pointerEvents: 'none', zIndex: 2147483647, alignItems: 'flex-end', justifyContent: 'flex-start', padding: width * 0.016}}>
    <div style={{maxWidth: '85%', background: 'rgba(0,0,0,0.78)', color: '#fff', padding: '0.45em 0.7em', borderRadius: 6, fontFamily: 'monospace', fontSize: Math.max(14, width / 80), lineHeight: 1.3, whiteSpace: 'pre-wrap', textAlign: 'right'}}>{reviewLabel(review, frame, fps)}</div>
  </AbsoluteFill>;
};
