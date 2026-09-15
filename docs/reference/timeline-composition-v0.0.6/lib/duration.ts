import type {TimelineClip, TimelineConfig} from '../types';

export type AstridRenderClock = {
  authored_duration_frames: number;
  render_duration_frames: number;
  tail: {
    policy: 'unmapped_excess_rendered_region';
    source_asset: string;
    start_frame: number;
    end_frame: number;
    source_start_frame: number;
    source_end_frame: number;
  };
};

export const secondsToFrames = (seconds: number, fps: number): number => {
  return Math.round(seconds * fps);
};

export const getClipSourceDuration = (clip: TimelineClip): number => {
  if (typeof clip.hold === 'number') {
    return clip.hold;
  }

  return (clip.to ?? 0) - (clip.from ?? 0);
};

export const getClipTimelineDuration = (clip: TimelineClip): number => {
  const speed = clip.speed ?? 1;
  return getClipSourceDuration(clip) / speed;
};

export const getSanitizedPlaybackRate = (speed: TimelineClip['speed']): number => {
  return typeof speed === 'number' && Number.isFinite(speed) && speed > 0 ? speed : 1;
};

export const getSanitizedVolume = (volume: number | undefined, fallback = 1): number => {
  return typeof volume === 'number' && Number.isFinite(volume)
    ? Math.max(0, volume)
    : fallback;
};

export const getClipDurationInFrames = (clip: TimelineClip, fps: number): number => {
  return Math.max(1, secondsToFrames(getClipTimelineDuration(clip), fps));
};

export const getAuthoredTimelineDurationInFrames = (timeline: TimelineConfig, fps: number): number => {
  return Math.max(
    1,
    ...timeline.clips.map((clip) => {
      return secondsToFrames(clip.at, fps) + getClipDurationInFrames(clip, fps);
    }),
  );
};

export const getRenderClock = (timeline: TimelineConfig): AstridRenderClock | null => {
  const app = (timeline as TimelineConfig & {app?: Record<string, unknown>}).app;
  const clock = app?.astrid_render_clock;
  return clock && typeof clock === 'object' ? clock as AstridRenderClock : null;
};

export const getTimelineDurationInFrames = (timeline: TimelineConfig, fps: number): number => {
  return getAuthoredTimelineDurationInFrames(timeline, fps);
};

export const getTimelineRenderDurationInFrames = (timeline: TimelineConfig, fps: number): number => {
  const authored = getAuthoredTimelineDurationInFrames(timeline, fps);
  const clock = getRenderClock(timeline);
  return clock?.render_duration_frames ?? authored;
};
