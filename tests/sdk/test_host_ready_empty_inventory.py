"""A freshly spawned empty-inventory host must match bootstrap's identity."""
import json
import subprocess
import sys

from astrid.core.gateway.dispatch import compose_profile_handoff


def test_ready_file_preserves_empty_inventory_identity(tmp_path):
    ready = tmp_path / 'ready.json'
    packs = tmp_path / 'packs'; packs.mkdir()
    support = tmp_path / 'support'; support.mkdir()
    manifest = support / 'astrid-host' / 'boot-manifest.json'
    compose_profile_handoff(manifest, support_root=support)
    result = subprocess.run([sys.executable, '-m', 'astrid.core.execution.generic_host',
        '--pack-root', str(packs), '--ready-file', str(ready),
        '--support-root', str(support),
        '--boot-manifest-path', str(manifest),
        '--source-inventory-identity', ''], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert json.loads(ready.read_text())['source_inventory_identity'] == ''
