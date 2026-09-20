import type {ReactElement} from 'react';
import {Img, staticFile} from 'remotion';
import {
  type ElementComponentProps,
  narrowParams,
} from '../../../../rendering/elements/_shared/contracts';

// Frame overlay (global border): fullscreen static frame over everything
// below. No phases; the clip hold carries the duration.
type Params = {
  __astridAssets?: Record<string, string>;
};

const renderableFile = (file: string | undefined): string | null => {
  if (!file || !file.trim()) return null;
  const value = file.trim();
  if (
    value.startsWith('http://')
    || value.startsWith('https://')
    || value.startsWith('/')
    || value.startsWith('blob:')
    || value.startsWith('data:')
  ) {
    return value;
  }
  return staticFile(value);
};

export default function FrameOverlay(
  props: ElementComponentProps,
): ReactElement | null {
  const params = narrowParams<Params>(props.params);
  const staged = params.__astridAssets ?? {};
  const src = renderableFile(staged.frame)
    ?? staticFile('astrid-effects/frame-overlay/frame.png');
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden'}}>
      <Img
        src={src}
        style={{position: 'absolute', inset: 0, width: '100%', height: '100%'}}
      />
    </div>
  );
}
