from __future__ import annotations

from pathlib import Path
from .models import SegmentMeta, StreamKey

BASE_DIR = Path("cluster/data")


def stream_dir(stream: StreamKey) -> Path:
    return BASE_DIR / stream.tenant_id / stream.app_id / stream.data_type / stream.schema_version


def current_log_path(stream: StreamKey) -> Path:
    return stream_dir(stream) / "current.jsonl"


def segments_dir(stream: StreamKey) -> Path:
    return stream_dir(stream) / "segments"


def segment_log_path(stream: StreamKey, segment_id: str) -> Path:
    return segments_dir(stream) / f"{segment_id}.jsonl"


def segment_meta_path(stream: StreamKey, segment_id: str) -> Path:
    return segments_dir(stream) / f"{segment_id}.meta.json"


def build_segment_file_name(meta: SegmentMeta) -> str:
    return f"{meta.segment_id}.jsonl"
