from pathlib import Path
bundle = Path('output/culter_multipurpose_bundle')
repo_out = Path('output/culter_multipurpose_repo_layout')
(repo_out / 'cluster/runtime').mkdir(parents=True, exist_ok=True)
(repo_out / 'docs').mkdir(parents=True, exist_ok=True)

mapping = {
    'models.py': 'cluster/runtime/models.py',
    'serialization.py': 'cluster/runtime/serialization.py',
    'paths.py': 'cluster/runtime/paths.py',
    'heartbeat_builder.py': 'cluster/runtime/heartbeat_builder.py',
    'noderuntime_patch.py': 'cluster/runtime/noderuntime.py',
    'apiapp_patch.py': 'cluster/runtime/apiapp.py',
    'eventlog_patch.py': 'cluster/runtime/eventlog.py',
    'dispatcher_patch.py': 'cluster/runtime/dispatcher.py',
    'reconciler_patch.py': 'cluster/runtime/reconciler_loop.py',
    'worker_patch.py': 'cluster/runtime/worker.py',
    'eventrouter_patch.py': 'cluster/runtime/eventrouter.py',
    'nodeworker_patch.py': 'cluster/runtime/nodeworker.py',
    'README.md': 'docs/README.md',
    'CHANGELOG.md': 'docs/CHANGELOG.md',
    '01_vision_arquitectura.md': 'docs/01_vision_arquitectura.md',
    '02_modelo_datos_python.md': 'docs/02_modelo_datos_python.md',
    '03_convenciones_ficheros.md': 'docs/03_convenciones_ficheros.md',
    '04_heartbeat_y_integridad.md': 'docs/04_heartbeat_y_integridad.md',
    '05_flujo_operativo.md': 'docs/05_flujo_operativo.md',
    '06_modelo_de_transicion.md': 'docs/06_modelo_de_transicion.md',
    '07_adapter_con_codigo_actual.md': 'docs/07_adapter_con_codigo_actual.md',
    'processo_path_retorno.md': 'docs/processo_path_retorno.md',
}

for src_name, dst_rel in mapping.items():
    src = bundle / src_name
    dst = repo_out / dst_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        dst.write_text(src.read_text(encoding='utf-8'), encoding='utf-8')

# create patch manifest
patch_lines = ['# Apply patch map', '']
for src_name, dst_rel in mapping.items():
    if src_name.endswith('.md'):
        continue
    patch_lines.append(f'- {src_name} -> {dst_rel}')
(repo_out / 'APPLY_PATCH_MAP.md').write_text('\n'.join(patch_lines) + '\n', encoding='utf-8')

# create top-level README
(repo_out / 'README.md').write_text('# Culter Multi Purpose Repo Layout\n\nEstructura propuesta lista para aplicar parches.\n', encoding='utf-8')

print('repo layout created')
