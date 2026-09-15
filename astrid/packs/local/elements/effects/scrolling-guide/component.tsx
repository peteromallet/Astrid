import type {ReactElement} from 'react';
import {interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {type ElementComponentProps, narrowParams} from '../../../../rendering/elements/_shared/contracts';

type GuideSection = {
  number: string;
  heading: string;
  lines: string[];
};

type Params = {
  heading?: string;
  subheading?: string;
  scrollStart?: number;
  scrollEnd?: number;
  sections?: GuideSection[];
};

const AMBER = '#ffa02e';
const CREAM = '#fff0db';
const MUTED = '#d5a76f';
const DESIGN_WIDTH = 1920;
const DESIGN_HEIGHT = 1080;

// Short excerpts preserve the actual Astrid workflow described in
// guides/matrix-minkhole-workflow.md and the video_editing pack guide. They
// are deliberately legible at the 640x360 review scale.
const DEFAULT_SECTIONS: GuideSection[] = [
  {number: '01', heading: 'FIND THE SOURCE', lines: ['Use the real shot', 'and its surrounding audio.']},
  {number: '02', heading: 'BUILD THE TIMELINE', lines: ['Arrange the picture', 'around the spoken beat.']},
  {number: '03', heading: 'ADD THE VOICEOVER', lines: ['Keep the phrase timing', 'and the natural pauses.']},
  {number: '04', heading: 'REVIEW THE CUT', lines: ['Render a concrete edit.', 'Scan the actual frames.']},
  {number: '05', heading: 'CHECK EACH TRANSITION', lines: ['Listen at the cut.', 'Compare the first and last word.']},
  {number: '06', heading: 'RENDER & OPEN', lines: ['Inspect the exported video', 'with labels and audio.']},
  {number: '07', heading: 'SAVE THE EVIDENCE', lines: ['Map the result back', 'to the owning clip.']},
];

const finitePositive = (value: unknown): number | null => (
  typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null
);

const validSections = (value: unknown): GuideSection[] => {
  if (!Array.isArray(value)) return DEFAULT_SECTIONS;
  const sections = value.filter((item): item is GuideSection => {
    if (!item || typeof item !== 'object') return false;
    const candidate = item as Partial<GuideSection>;
    return typeof candidate.number === 'string'
      && typeof candidate.heading === 'string'
      && Array.isArray(candidate.lines)
      && candidate.lines.every((line) => typeof line === 'string');
  });
  return sections.length > 0 ? sections : DEFAULT_SECTIONS;
};

function GuideSectionRow({section, top}: {section: GuideSection; top: number}): ReactElement {
  return <div style={{position: 'absolute', left: 34, top, width: 820, height: 124, borderBottom: `2px solid rgba(255,160,46,0.42)`}}>
    <div style={{position: 'absolute', left: 0, top: 4, color: AMBER, fontFamily: 'monospace', fontSize: 19, letterSpacing: 3}}>{section.number}</div>
    <div style={{position: 'absolute', left: 56, top: 0, color: CREAM, fontFamily: 'monospace', fontSize: 25, fontWeight: 700, letterSpacing: 3, whiteSpace: 'nowrap'}}>{section.heading}</div>
    <div style={{position: 'absolute', left: 56, top: 45, color: MUTED, fontFamily: 'monospace', fontSize: 22, lineHeight: 1.45, letterSpacing: 1}}>
      {section.lines.map((line, index) => <div key={`${section.number}-${index}`}>{line}</div>)}
    </div>
  </div>;
}

export default function ScrollingGuide({clip, params: rawParams, fps}: ElementComponentProps): ReactElement {
  const frame = useCurrentFrame();
  const {width} = useVideoConfig();
  const params = narrowParams<Params>(rawParams);
  const sections = validSections(params.sections);
  const clipSeconds = finitePositive(clip.hold) ?? finitePositive((clip.to ?? 0) - clip.at) ?? 9.548;
  const elapsed = frame / fps;
  const scrollStart = Math.max(0, params.scrollStart ?? 0);
  const scrollEnd = Math.max(scrollStart, params.scrollEnd ?? 440);
  const scroll = interpolate(elapsed, [0, clipSeconds], [scrollStart, scrollEnd], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const totalContentHeight = sections.length * 124;
  const viewportHeight = 590;
  const scale = width / DESIGN_WIDTH;
  const heading = params.heading ?? 'MAKING VIDEOS';
  const subheading = params.subheading ?? 'A SMALL GUIDE TO THE REVIEW LOOP';

  // This is a self-contained authored-canvas group. It scales with the
  // Remotion composition when a small explicit canvas is used, while the
  // normal review path keeps the authored 1920x1080 geometry and applies
  // backend --scale at export time.
  return <div style={{position: 'absolute', inset: 0, overflow: 'hidden', pointerEvents: 'none'}}>
    <div style={{position: 'absolute', left: 0, top: 0, width: DESIGN_WIDTH, height: DESIGN_HEIGHT, transform: `scale(${scale})`, transformOrigin: 'top left'}}>
      <div style={{position: 'absolute', left: 850, top: 126, width: 900, height: 748, color: CREAM, backgroundColor: 'rgba(9,6,3,0.96)', border: `4px solid ${AMBER}`, boxShadow: `0 0 42px rgba(255,160,46,0.38)`}}>
        <div style={{position: 'absolute', left: 28, right: 28, top: 22, height: 76, borderBottom: `3px solid ${AMBER}`}}>
          <div style={{color: AMBER, fontFamily: 'monospace', fontSize: 43, fontWeight: 700, letterSpacing: 5}}>{heading}</div>
          <div style={{marginTop: 8, color: MUTED, fontFamily: 'monospace', fontSize: 17, letterSpacing: 3}}>{subheading}</div>
          <div style={{position: 'absolute', right: 0, top: 4, color: AMBER, fontFamily: 'monospace', fontSize: 18, letterSpacing: 2}}>GUIDE / 01</div>
        </div>
        <div style={{position: 'absolute', left: 28, top: 122, width: 844, height: viewportHeight, overflow: 'hidden'}}>
          <div style={{position: 'absolute', left: 0, top: -scroll, width: 844, height: totalContentHeight}}>
            {sections.map((section, index) => <GuideSectionRow key={`${section.number}-${index}`} section={section} top={index * 124} />)}
          </div>
          <div style={{position: 'absolute', left: 0, right: 0, top: 0, height: 30, background: 'linear-gradient(180deg, rgba(9,6,3,0.35), rgba(9,6,3,0))'}} />
          <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 54, background: 'linear-gradient(0deg, rgba(9,6,3,0.98), rgba(9,6,3,0))'}} />
        </div>
        <div style={{position: 'absolute', left: 28, right: 28, bottom: 22, height: 10, border: `2px solid ${AMBER}`}}>
          <div style={{height: '100%', width: `${Math.max(2, Math.min(100, ((scroll - scrollStart) / Math.max(1, scrollEnd - scrollStart)) * 100))}%`, backgroundColor: AMBER}} />
        </div>
      </div>
    </div>
  </div>;
}
