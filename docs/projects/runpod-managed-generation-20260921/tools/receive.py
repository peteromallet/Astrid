#!/usr/bin/env python3
"""Retrieve locked public sources into NEW directories. Never run source code."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess


def git(args, cwd=None):
    env = os.environ.copy()
    env.update(GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_LFS_SKIP_SMUDGE='1')
    for key in list(env):
        if key.startswith('GIT_CONFIG_KEY_') or key.startswith('GIT_CONFIG_VALUE_') or key in ('GIT_CONFIG_COUNT', 'GIT_ASKPASS', 'SSH_ASKPASS'):
            env.pop(key, None)
    return subprocess.run(['git', '-c', 'credential.helper=', '-c', 'core.hooksPath=/dev/null', *args],
                          cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=240)


def retrieve(row, parent):
    name, url, sha = row['id'], row['url'], row['sha']
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', name) or not re.fullmatch('[0-9a-f]{40}', sha) or not url.startswith('https://github.com/') or '@' in url:
        raise ValueError('Invalid lock entry')
    target = parent / (name + '-' + sha[:12])
    result = {'id': name, 'url': url, 'requested_sha': sha, 'destination': target.name, 'status': 'PENDING'}
    if target.exists() or target.is_symlink():
        return dict(result, status='REFUSED_EXISTING_DESTINATION')
    try:
        command = git(['clone', '--no-checkout', '--filter=blob:none', '--depth=1', '--no-recurse-submodules', url, str(target)])
        if command.returncode:
            return dict(result, status='CLONE_UNAVAILABLE', reason='Anonymous public clone failed; verify URL/access/network. No source substitution.')
        exact = git(['fetch', '--depth=1', 'origin', sha], target)
        if exact.returncode:
            # Bounded public-ref fallback; still require the original SHA.
            fallback = git(['fetch', '--filter=blob:none', '--depth=256', 'origin', '+refs/heads/*:refs/remotes/origin/*', '+refs/tags/*:refs/tags/*'], target)
            if git(['cat-file', '-e', sha + '^{commit}'], target).returncode:
                return dict(result, status='PIN_UNAVAILABLE', fallback='Exact fetch and depth-256 branch/tag fetch could not resolve pin. Publisher must expose the same object at a public ref; no automatic latest replacement.')
        checkout = git(['checkout', '--detach', sha], target)
        if checkout.returncode:
            return dict(result, status='CHECKOUT_FAILED', reason='Exact object or required blobs unavailable; preserved partial checkout for inspection.')
        observed = git(['rev-parse', 'HEAD'], target).stdout.strip()
        tree = git(['rev-parse', 'HEAD^{tree}'], target).stdout.strip()
        dirty = git(['status', '--porcelain'], target).stdout.strip()
        return dict(result, status='PASS' if observed == sha and not dirty else 'IDENTITY_MISMATCH', observed_sha=observed, tree=tree, clean=not dirty)
    except subprocess.TimeoutExpired:
        return dict(result, status='TIMEOUT', reason='Bounded public Git operation exceeded 240 seconds. Use a new parent for retry.')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--lock', type=Path, default=Path(__file__).resolve().parents[1] / 'repo-lock.json')
    p.add_argument('--destination', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    if a.destination.exists() or a.destination.is_symlink() or a.report.exists() or a.report.is_symlink():
        raise SystemExit('Refusing existing destination/report; choose fresh names')
    a.destination.mkdir(parents=False, mode=0o700)
    rows = json.loads(a.lock.read_text())['repositories']
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda row: retrieve(row, a.destination), rows))
    report = {'scope': 'public exact source retrieval only; no installation, tests, models, provider calls or acceptance', 'repositories': results}
    with a.report.open('x') as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write('\n')
    for row in results:
        print(row['id'] + ': ' + row['status'])
    raise SystemExit(0 if all(x['status'] == 'PASS' for x in results) else 2)
