"""Public grammar for rendered continuity inspection, shared by SDK and runner."""
from __future__ import annotations

import math
from typing import Any, Mapping


def seconds(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError('time must be seconds or [HH:]MM:SS')
    try:
        parts = str(value).split(':')
        if len(parts) > 3:
            raise ValueError
        numbers = [float(part) for part in parts]
        if any(not math.isfinite(n) or n < 0 for n in numbers):
            raise ValueError
        if len(numbers) > 1 and any(n >= 60 for n in numbers[1:]):
            raise ValueError
        result = 0.0
        for number in numbers:
            result = result * 60 + number
    except (TypeError, ValueError):
        raise ValueError('time must be seconds or [HH:]MM:SS') from None
    if not math.isfinite(result) or result < 0:
        raise ValueError('time must be finite and non-negative')
    return result


def filmstrip_options(values: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize only public controls; never accept an unbounded sampling job."""
    sample = values.get('sample') or 'interval'
    if sample not in {'interval', 'clips', 'shots', 'cuts'}:
        raise ValueError('sample must be interval, clips, shots, or cuts')
    every, frames = values.get('every'), values.get('every_frames')
    if every is not None and frames is not None:
        raise ValueError('choose every seconds or every_frames, not both')
    if frames is not None and (type(frames) is not int or frames < 1):
        raise ValueError('every_frames must be a positive integer')
    if every is not None and (isinstance(every, bool) or not isinstance(every, (float, int))
                              or not math.isfinite(every) or every <= 0):
        raise ValueError('every must be a finite positive number of seconds')
    if sample != 'interval' and (every is not None or frames is not None):
        raise ValueError('every/every_frames apply only to sample=interval')
    result: dict[str, Any] = {'sample': sample, 'every': every if every is not None else (None if frames else 0.5),
                              'every_frames': frames, 'max_frames': 2000,
                              'include_media': bool(values.get('include_media', False))}
    for name, default, maximum in [('columns', 5, 8), ('page_size', 50, 100)]:
        n = values.get(name, default)
        if n is None:
            n = default
        if type(n) is not int or not 1 <= n <= maximum:
            raise ValueError(f'{name} must be an integer between 1 and {maximum}')
        result[name] = n
    window, at = values.get('range'), values.get('at')
    if window is not None and at is not None:
        raise ValueError('choose range or at, not both')
    if window is not None:
        if isinstance(window, str):
            window = window.split('..')
        if not isinstance(window, (list, tuple)) or len(window) != 2:
            raise ValueError('range must be START..END')
        start, end = map(seconds, window)
        if end <= start:
            raise ValueError('range end must follow its start')
        result['range'] = [start, end]
    if at is not None:
        result['at'] = seconds(at)
    context = values.get('context', 3.0)
    result['context'] = seconds(3.0 if context is None else context)
    if at is not None and result['context'] <= 0:
        raise ValueError('context must be positive when focusing a timestamp')
    for name in ('clip', 'shot', 'asset'):
        if values.get(name) not in (None, ''):
            if not isinstance(values[name], str):
                raise ValueError(f'{name} must be an identifier')
            result[name] = values[name]
    return result
