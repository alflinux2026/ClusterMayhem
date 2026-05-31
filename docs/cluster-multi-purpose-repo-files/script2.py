from pathlib import Path
out = Path('output')
out.mkdir(exist_ok=True)

# Create a simple consolidated diff-like manifest for the files we generated.
repo_layout = Path('output/culter_multipurpose_repo_layout')
files = [
    'cluster/runtime/models.py',
    'cluster/runtime/serialization.py',
    'cluster/runtime/paths.py',
    'cluster/runtime/heartbeat_builder.py',
    'cluster/runtime/noderuntime.py',
    'cluster/runtime/apiapp.py',
    'cluster/runtime/eventlog.py',
    'cluster/runtime/dispatcher.py',
    'cluster/runtime/reconciler_loop.py',
    'cluster/runtime/worker.py',
    'cluster/runtime/eventrouter.py',
    'cluster/runtime/nodeworker.py',
]

lines = ['# Diff map', '']
for rel in files:
    p = repo_layout / rel
    lines.append(f'## {rel}')
    lines.append('```diff')
    if p.exists():
        content = p.read_text(encoding='utf-8').splitlines()
        for line in content[:80]:
            if line.startswith('from ') or line.startswith('import '):
                lines.append(f'+ {line}')
            elif line.strip().startswith('class ') or line.strip().startswith('def '):
                lines.append(f'+ {line}')
            elif line.strip().startswith('@dataclass'):
                lines.append(f'+ {line}')
    lines.append('```')
    lines.append('')

(out / 'culter_multipurpose_diff_map.md').write_text('\n'.join(lines), encoding='utf-8')
print('diff map created')
