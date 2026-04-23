from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from market_analytics.io import load_and_validate_datasets
from market_analytics.public_snapshots import build_public_snapshots
from market_analytics.reporting import build_analytics_outputs, save_analytics_outputs

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNTIME_DATABASES: tuple[Path, ...] = (
    PROJECT_ROOT / "runtime" / "jobs_ch" / "main-config" / "jobs_ch.sqlite",
    PROJECT_ROOT / "runtime" / "jobscout24_ch" / "main-config" / "jobscout24_ch.sqlite",
    PROJECT_ROOT / "runtime" / "jobup_ch" / "main-config" / "jobup_ch.sqlite",
    PROJECT_ROOT / "runtime" / "linked_in" / "main-config" / "linked_in.sqlite",
    PROJECT_ROOT / "runtime" / "swissdevjobs_ch" / "main-config" / "swissdevjobs_ch.sqlite",
)
DEFAULT_ANALYTICS_OUTPUT_DIR = PROJECT_ROOT / "analytics_output"
DEFAULT_PUBLIC_STATS_DIR = PROJECT_ROOT / "public_stats" / "data"
DEFAULT_PUBLIC_CSV_DIR = PROJECT_ROOT / "public_stats" / "csv"


def resolve_runtime_dataset_paths(dataset_paths: Iterable[str | Path] | None = None) -> list[Path]:
    if dataset_paths is None:
        resolved = [path for path in DEFAULT_RUNTIME_DATABASES if path.is_file()]
    else:
        resolved = [Path(path) for path in dataset_paths]

    missing = [path for path in resolved if not path.is_file()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Dataset file not found: {missing_text}")
    if not resolved:
        raise FileNotFoundError("No runtime SQLite datasets found to rebuild statistics.")
    return resolved


def rebuild_runtime_statistics(
    *,
    dataset_paths: Sequence[str | Path] | None = None,
    analytics_output_dir: str | Path = DEFAULT_ANALYTICS_OUTPUT_DIR,
    public_stats_dir: str | Path = DEFAULT_PUBLIC_STATS_DIR,
    public_csv_dir: str | Path = DEFAULT_PUBLIC_CSV_DIR,
    top_skills_limit: int = 20,
    top_skill_pairs_limit: int = 50,
) -> tuple[list[Path], list[Path], list[Path]]:
    resolved_dataset_paths = resolve_runtime_dataset_paths(dataset_paths)
    analytics_output_path = Path(analytics_output_dir)
    public_stats_path = Path(public_stats_dir)
    public_csv_path = Path(public_csv_dir)

    dataset = load_and_validate_datasets(resolved_dataset_paths)
    outputs = build_analytics_outputs(
        dataset=dataset,
        top_skills_limit=top_skills_limit,
        top_skill_pairs_limit=top_skill_pairs_limit,
    )
    analytics_paths = save_analytics_outputs(outputs, analytics_output_path)
    public_paths = build_public_snapshots(
        csv_dir=analytics_output_path,
        output_dir=public_stats_path,
        copy_csv_dir=public_csv_path,
    )
    return resolved_dataset_paths, analytics_paths, public_paths
