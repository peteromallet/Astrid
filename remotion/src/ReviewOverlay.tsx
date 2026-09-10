import type {ReactElement} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';

export type ReviewContext = {
  shots: Array<{shot_id: string; name: string; at: number; hold: number}>;
  speech?: {
    status?: string;
    phrases?: Array<{
      id?: string;
      text?: string;
      status?: string;
      render_interval?: {
        start?: number | [number, number];
        end?: number | [number, number];
      } | null;
    }>;
  };
};

const intervalNumber = (value: number | [number, number] | undefined): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (Array.isArray(value) && value.length === 2 && Number.isFinite(value[0]) && Number.isFinite(value[1]) && value[1] !== 0) {
    return value[0] / value[1];
  }
  return null;
};

export const reviewCaption = (review: ReviewContext, frame: number, fps: number): string | null => {
  const time = frame / fps;
  const phrases = review.speech?.phrases ?? [];
  const active = phrases
    .map((phrase, index) => ({phrase, index, start: intervalNumber(phrase.render_interval?.start), end: intervalNumber(phrase.render_interval?.end)}))
    .filter(item => item.phrase.status === 'projected' && typeof item.phrase.text === 'string' && item.phrase.text.trim() && item.start !== null && item.end !== null && time >= item.start && time < item.end)
    .sort((a, b) => (b.start as number) - (a.start as number) || a.index - b.index);
  return active[0]?.phrase.text?.trim() ?? null;
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
  const {fps, width, height} = useVideoConfig();
  if (!review) return null;
  const caption = reviewCaption(review, frame, fps);
  return <AbsoluteFill style={{pointerEvents: 'none', zIndex: 2147483647}}>
    <AbsoluteFill style={{alignItems: 'flex-end', justifyContent: 'flex-start', padding: width * 0.016}}>
      <div style={{maxWidth: '85%', background: 'rgba(0,0,0,0.78)', color: '#fff', padding: '0.45em 0.7em', borderRadius: 6, fontFamily: 'monospace', fontSize: Math.max(14, width / 80), lineHeight: 1.3, whiteSpace: 'pre-wrap', textAlign: 'right'}}>{reviewLabel(review, frame, fps)}</div>
    </AbsoluteFill>
    {caption ? <div style={{position: 'absolute', left: '1%', right: '1%', bottom: '1%', minHeight: height * 0.24, boxSizing: 'border-box', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#000', padding: `${height * 0.025}px ${width * 0.06}px`}}>
      <div style={{maxWidth: '90%', color: '#fff', fontFamily: 'Arial, sans-serif', fontSize: Math.max(22, width / 48), fontWeight: 600, lineHeight: 1.25, whiteSpace: 'pre-wrap', textAlign: 'center'}}>{caption}</div>
    </div> : null}
  </AbsoluteFill>;
};
