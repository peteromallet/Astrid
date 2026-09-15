import type {ReactElement} from 'react';
import {Img, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {Video} from '@remotion/media';
import {type ElementComponentProps, narrowParams} from '../../../../rendering/elements/_shared/contracts';

type TimelineSegment = {
  id?: string;
  start: number;
  end: number;
  sourceStart?: number;
  sourceEnd?: number;
  speed?: number;
  label: string;
  title: string;
};
type PhaseDurations = {prep?: number; iteration?: number; anchors?: number; workflow?: number};
type Params = {
  __astridAssets?: Record<string, string>;
  phaseDurations?: PhaseDurations;
  prepSeconds?: number;
  iterationSeconds?: number;
  anchorsSeconds?: number;
  workflowSeconds?: number;
  prepSourceStart?: number;
  prepSourceEnd?: number;
  prepSourceSpeed?: number;
  timelineSegments?: TimelineSegment[];
  selectedSegmentId?: string;
  selectedSegmentIndex?: number;
  headings?: Partial<Record<'prep' | 'iteration' | 'anchors' | 'workflow', string>>;
};

const AMBER = '#ffa02e';
const INK = '#0b0703';
// The six canonical Minkhole thumbnails are all 16:9. Keep legacy effect
// cards out of the keyframe flicker so every reference uses the same frame
// geometry as the source visualizer.
const CARD_KEYS = ['card0', 'card1', 'card2', 'card3', 'card4', 'card5'] as const;
// Six real sections from the final child-16 Minkhole timeline. Callers can
// replace this with the current visualizer snapshot through params.
const DEFAULT_SEGMENTS: TimelineSegment[] = [
  {id: 'astrid', start: 0, end: 5, label: '00', title: 'ASTRID — through the glasses'},
  {id: 'choice', start: 5, end: 8, sourceStart: 74.9347, sourceEnd: 76.4, speed: 0.4884, label: '01', title: 'Two options'},
  {id: 'blue', start: 8, end: 19, sourceStart: 79.12, sourceEnd: 80.87, label: '02', title: 'Blue pill — manual tools'},
  {id: 'red', start: 19, end: 22, label: '03', title: 'Red pill'},
  {id: 'creature', start: 22, end: 26.9167, label: '04', title: 'Creature reveal — glasses edit'},
  {id: 'reflection', start: 26.9167, end: 43.4927, label: '05', title: 'Into the minkhole — reflection close-up'},
];
const DEFAULT_HEADINGS = {
  prep: 'Original clip + rough voiceover',
  iteration: 'Words & timing',
  anchors: 'Anchor frames',
  workflow: 'Workflow running',
} as const;
const ITERATION_ORDER = [2, 0, 4, 1, 5, 3] as const;
const DEFAULT_SELECTED_SEGMENT_INDEX = 2;
const ITERATION_WORDS = [
  'You have two options.',
  'You take the blue pill.',
  'You take the red pill.',
] as const;
const ROW_LEFT = 120;
const ROW_STEP = 300;
const CARD_WIDTH = 240;
const CARD_HEIGHT = 135;

const clamp = (value: number): number => Math.max(0, Math.min(1, value));
const phase = (value: number, start: number, end: number): number => interpolate(value, [start, end], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
const positive = (value: unknown): number | null => typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null;

const phaseValues = (params: Params, clipSeconds: number): [number, number, number, number] => {
  const configured = params.phaseDurations ?? {};
  const values = [
    positive(params.prepSeconds) ?? positive(configured.prep),
    positive(params.iterationSeconds) ?? positive(configured.iteration),
    positive(params.anchorsSeconds) ?? positive(configured.anchors),
    positive(params.workflowSeconds) ?? positive(configured.workflow),
  ];
  if (values.every((value): value is number => value !== null)) return values as [number, number, number, number];
  // Keep the visual sequence adaptable when narration lengths change and the
  // timeline owner omits explicit phase metadata.
  return [0.24, 0.22, 0.2, 0.34].map((weight) => clipSeconds * weight) as [number, number, number, number];
};

const validSegments = (value: unknown): TimelineSegment[] => {
  if (!Array.isArray(value)) return DEFAULT_SEGMENTS;
  const result = value.filter((segment): segment is TimelineSegment => {
    if (!segment || typeof segment !== 'object') return false;
    const candidate = segment as Partial<TimelineSegment>;
    return typeof candidate.start === 'number' && Number.isFinite(candidate.start)
      && typeof candidate.end === 'number' && Number.isFinite(candidate.end) && candidate.end > candidate.start
      && typeof candidate.label === 'string' && candidate.label.length > 0
      && typeof candidate.title === 'string' && candidate.title.length > 0;
  });
  return result.length > 0 ? result : DEFAULT_SEGMENTS;
};

const renderableFile = (file: string | undefined): string | null => {
  if (!file || !file.trim()) return null;
  return file.startsWith('http://') || file.startsWith('https://') ? file : staticFile(file);
};

type TimelineStripProps = {
  segments: TimelineSegment[];
  cards: string[];
  rowY: number;
  progress: number;
  selectedIndex: number | null;
  mode: 'prep' | 'iteration' | 'anchors' | 'workflow';
  url: (key: string) => string;
};

function TimelineStrip({segments, cards, rowY, progress, selectedIndex, mode, url}: TimelineStripProps): ReactElement {
  return <div style={{position: 'absolute', left: 960, top: rowY, transform: 'translateX(-50%)', width: 1760, height: 290}}>
    <div style={{position: 'absolute', left: 0, right: 0, top: 150, height: 6, backgroundColor: AMBER, boxShadow: `0 0 24px ${AMBER}`}} />
    {segments.map((segment, index) => {
      // The words/timing phase is the only phase that reorders cards. Anchors
      // and workflow show the source timeline in canonical chronological order.
      const targetSlot = mode === 'iteration' ? ITERATION_ORDER[index] ?? index : index;
      const slot = mode === 'prep' ? index : interpolate(progress, [0, 1], [index, targetSlot], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
      const x = ROW_LEFT + slot * ROW_STEP;
      const entering = mode === 'prep' ? phase(progress, index / segments.length * 0.78, index / segments.length * 0.78 + 0.12) : 1;
      const active = selectedIndex === index;
      return <div key={segment.id ?? `${segment.label}-${index}`} style={{position: 'absolute', left: x - CARD_WIDTH / 2, top: 150 - CARD_HEIGHT / 2, width: CARD_WIDTH, opacity: entering, transform: `scale(${active ? 1.08 : 1})`, transformOrigin: 'center center'}}>
        <div style={{position: 'absolute', inset: -10, border: `3px solid ${AMBER}`, boxShadow: active || mode === 'anchors' ? `0 0 34px ${AMBER}` : 'none', opacity: active ? 0.95 : 0.28}} />
        <Img src={url(cards[index % cards.length])} style={{display: 'block', width: CARD_WIDTH, height: CARD_HEIGHT, objectFit: 'cover', border: `2px solid ${INK}`}} />
        <div style={{marginTop: 16, width: CARD_WIDTH, overflow: 'hidden', textOverflow: 'ellipsis', color: active ? '#fff0db' : '#ffd6a3', fontFamily: 'monospace', fontSize: 16, letterSpacing: 2, textAlign: 'center', whiteSpace: 'nowrap'}}>{segment.label} · {segment.title}</div>
      </div>;
    })}
  </div>;
}

function Heading({text}: {text: string}): ReactElement {
  return <div style={{position: 'absolute', left: 220, right: 220, top: 790, color: AMBER, fontFamily: 'monospace', fontSize: 27, letterSpacing: 8, textAlign: 'center', textTransform: 'uppercase'}}>{text}</div>;
}

function IterationWords({progress}: {progress: number}): ReactElement {
  const index = Math.min(ITERATION_WORDS.length - 1, Math.floor(clamp(progress) * ITERATION_WORDS.length));
  return <div style={{position: 'absolute', left: 320, right: 320, top: 738, height: 30, color: '#fff0db', fontFamily: 'monospace', fontSize: 22, letterSpacing: 3, textAlign: 'center', textTransform: 'uppercase', whiteSpace: 'nowrap'}}>
    {ITERATION_WORDS.map((word, wordIndex) => <span key={word} style={{position: 'absolute', inset: 0, opacity: wordIndex === index ? 1 : 0, transition: 'opacity 80ms linear'}}>{word}</span>)}
  </div>;
}

export default function EndSpanningLayer({clip, params: rawParams, assetEntry, fps}: ElementComponentProps): ReactElement | null {
  const frame = useCurrentFrame();
  const params = narrowParams<Params>(rawParams);
  const clipSeconds = positive(clip.hold) ?? positive((clip.to ?? 0) - clip.at) ?? 30;
  const [prepSeconds, iterationSeconds, anchorsSeconds, workflowSeconds] = phaseValues(params, clipSeconds);
  const prepEnd = prepSeconds;
  const iterationEnd = prepEnd + iterationSeconds;
  const anchorsEnd = iterationEnd + anchorsSeconds;
  const elapsed = frame / fps;
  const prepP = phase(elapsed, 0, prepEnd);
  const iterationP = phase(elapsed, prepEnd, iterationEnd);
  const anchorsP = phase(elapsed, iterationEnd, anchorsEnd);
  const workflowP = phase(elapsed, anchorsEnd, anchorsEnd + workflowSeconds);
  const mode: TimelineStripProps['mode'] = elapsed < prepEnd ? 'prep' : elapsed < iterationEnd ? 'iteration' : elapsed < anchorsEnd ? 'anchors' : 'workflow';
  const segments = validSegments(params.timelineSegments);
  const cards = [...CARD_KEYS];
  const staged = params.__astridAssets ?? {};
  const url = (key: string): string => staged[key] ? staticFile(staged[key]) : staticFile(`astrid-effects/end-spanning-layer/${key}`);
  const fallbackSelectedIndex = Math.min(segments.length - 1, DEFAULT_SELECTED_SEGMENT_INDEX);
  const requestedIndex = typeof params.selectedSegmentIndex === 'number' && Number.isFinite(params.selectedSegmentIndex) && params.selectedSegmentIndex >= 0
    ? params.selectedSegmentIndex
    : null;
  const selectedIndex = mode === 'workflow' ? (
    typeof params.selectedSegmentId === 'string'
      ? Math.max(0, segments.findIndex((segment) => segment.id === params.selectedSegmentId))
      : requestedIndex === null ? fallbackSelectedIndex : Math.min(segments.length - 1, Math.floor(requestedIndex))
  ) : null;
  const selected = selectedIndex === null ? null : segments[selectedIndex];
  const sourceStart = selected ? positive(selected.sourceStart) ?? selected.start : 0;
  const sourceEnd = selected ? positive(selected.sourceEnd) ?? selected.end : 1;
  const sourceSpeed = selected ? positive(selected.speed) ?? 1 : 1;
  const prepSourceStart = positive(params.prepSourceStart) ?? 74.08;
  const prepSourceEnd = positive(params.prepSourceEnd) ?? 84.3;
  const prepSourceSpeed = positive(params.prepSourceSpeed) ?? 1;
  const sourceUrl = renderableFile(assetEntry?.file);
  const heading = params.headings?.[mode] ?? DEFAULT_HEADINGS[mode];
  const fadeOut = mode === 'workflow' ? 1 - phase(workflowP, 0.92, 1) : 1;
  const flickerIndex = Math.floor(anchorsP * 12) % cards.length;
  const flickerPrevious = (flickerIndex + cards.length - 1) % cards.length;
  const stripProgress = mode === 'prep' ? prepP : mode === 'iteration' ? iterationP : mode === 'anchors' ? anchorsP : workflowP;
  // Center the effect's own visual bounds on the authored canvas. These
  // offsets are deliberately independent of ReviewOverlay subtitles: the
  // content should occupy the frame naturally and captions may overlay it.
  const contentShiftY = mode === 'iteration' ? -140 : mode === 'anchors' ? 100 : 105;

  return <div style={{position: 'absolute', inset: 0, overflow: 'hidden', opacity: fadeOut, backgroundColor: 'transparent'}}>
    <div style={{position: 'absolute', inset: 0, transform: `translateY(${contentShiftY}px)`}}>
      {mode === 'prep' && sourceUrl ? <div style={{position: 'absolute', left: 520, top: 44, width: 880, height: 430, border: `4px solid ${AMBER}`, boxShadow: '0 0 45px rgba(255,160,46,0.5)', overflow: 'hidden', backgroundColor: INK}}>
        <Video src={sourceUrl} trimBefore={prepSourceStart * fps} trimAfter={prepSourceEnd * fps} playbackRate={prepSourceSpeed} muted loop style={{width: '100%', height: '100%', objectFit: 'cover'}} />
        <div style={{position: 'absolute', left: 24, top: 18, color: '#fff0db', fontFamily: 'monospace', fontSize: 22, letterSpacing: 4, textShadow: '0 2px 8px #000'}}>ORIGINAL CLIP + ROUGH VOICEOVER</div>
      </div> : null}
      {mode === 'anchors' ? <div style={{position: 'absolute', left: 570, top: 62, width: 780, height: 438, border: `3px solid ${AMBER}`, boxShadow: `0 0 42px rgba(255,160,46,${0.25 + anchorsP * 0.35})`, overflow: 'hidden', backgroundColor: INK}}>
        <Img src={url(cards[flickerPrevious])} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', opacity: 1 - anchorsP}} />
        <Img src={url(cards[flickerIndex])} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', opacity: 0.55 + anchorsP * 0.45}} />
        <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(180deg, transparent 35%, rgba(8,5,2,0.88) 100%)'}} />
        <div style={{position: 'absolute', left: 24, bottom: 20, color: '#fff0db', fontFamily: 'monospace', fontSize: 22, letterSpacing: 4}}>KEYFRAME REFERENCE</div>
      </div> : null}
      {mode === 'workflow' && sourceUrl && selected ? <div style={{position: 'absolute', left: 520, top: 44, width: 880, height: 430, border: `4px solid ${AMBER}`, boxShadow: '0 0 45px rgba(255,160,46,0.5)', overflow: 'hidden', backgroundColor: INK}}>
        <Video src={sourceUrl} trimBefore={sourceStart * fps} trimAfter={sourceEnd * fps} playbackRate={sourceSpeed} muted loop style={{width: '100%', height: '100%', objectFit: 'cover'}} />
        <div style={{position: 'absolute', left: 24, top: 18, color: '#fff0db', fontFamily: 'monospace', fontSize: 22, letterSpacing: 4, textShadow: '0 2px 8px #000'}}>MINKHOLE OUTPUT · {selected.label}</div>
      </div> : null}
      <TimelineStrip segments={segments} cards={cards} rowY={460} progress={stripProgress} selectedIndex={selectedIndex} mode={mode} url={url} />
      {mode === 'iteration' ? <IterationWords progress={iterationP} /> : null}
      <Heading text={heading} />
    </div>
  </div>;
}
