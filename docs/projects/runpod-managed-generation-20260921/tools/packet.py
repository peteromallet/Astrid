#!/usr/bin/env python3
"""Standard-library-only packet hashing, safe extraction and deterministic ZIP."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or any(x in ('', '.', '..') for x in name.split('/')) or '\\' in name or ':' in name or '\x00' in name:
        raise ValueError('Unsafe path: ' + repr(name))
    return p


def census(root):
    paths = []
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise ValueError('Symlink forbidden: ' + str(p))
        if p.is_file():
            safe(p.relative_to(root).as_posix())
            paths.append(p)
    return paths


def verify(root):
    lines = (root / 'SHA256SUMS').read_text().splitlines()
    expected = {}
    for line in lines:
        sha, name = line.split('  ', 1)
        safe(name)
        if name in expected or not re.fullmatch('[0-9a-f]{64}', sha):
            raise ValueError('Invalid/duplicate checksum entry')
        expected[name] = sha
    actual = {p.relative_to(root).as_posix(): digest(p.read_bytes()) for p in census(root) if p.name != 'SHA256SUMS'}
    if actual != expected:
        raise ValueError('Checksum or file census mismatch')
    for p in census(root):
        if p.suffix != '.md':
            continue
        for target in re.findall(r'\]\(([^)]+)\)', p.read_text()):
            target = target.split('#')[0]
            if not target or '://' in target or target.startswith('mailto:'):
                continue
            resolved = (p.parent / target).resolve()
            if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
                raise ValueError(f'Broken/nonportable link: {p.relative_to(root)} -> {target}')
    return {'files_verified': len(expected), 'hashes': 'PASS', 'paths': 'PASS', 'markdown_links': 'PASS'}


def seal(root):
    rows = [f'{digest(p.read_bytes())}  {p.relative_to(root).as_posix()}\n' for p in census(root) if p.name != 'SHA256SUMS']
    (root / 'SHA256SUMS').write_text(''.join(rows))


def build(root, output):
    verify(root)
    if output.exists() or output.is_symlink():
        raise ValueError('Refusing overwrite: ' + str(output))
    # ZIP_STORED avoids compression-library version differences.
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_STORED) as z:
        for p in census(root):
            item = zipfile.ZipInfo(p.relative_to(root).as_posix(), (1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.external_attr = (stat.S_IFREG | 0o644) << 16
            item.compress_type = zipfile.ZIP_STORED
            z.writestr(item, p.read_bytes())
    return digest(output.read_bytes())


def extract(archive, dest, expected):
    if digest(archive.read_bytes()) != expected:
        raise ValueError('Archive SHA-256 mismatch')
    if dest.exists() or dest.is_symlink():
        raise ValueError('Refusing existing extraction destination')
    with zipfile.ZipFile(archive) as z:
        names = set()
        for i in z.infolist():
            safe(i.filename)
            mode = i.external_attr >> 16
            if i.filename in names or i.is_dir() or stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise ValueError('Duplicate or nonregular archive member')
            names.add(i.filename)
        dest.mkdir(mode=0o700, parents=False, exist_ok=False)
        for i in z.infolist():
            target = dest / i.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(z.read(i))
    return verify(dest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['seal', 'verify', 'build', 'extract'])
    parser.add_argument('path', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--sha256')
    args = parser.parse_args()
    if args.action == 'seal':
        seal(args.path)
    elif args.action == 'verify':
        print(json.dumps(verify(args.path), indent=2))
    elif args.action == 'build':
        print(build(args.path, args.output))
    else:
        print(json.dumps(extract(args.path, args.output, args.sha256), indent=2))
