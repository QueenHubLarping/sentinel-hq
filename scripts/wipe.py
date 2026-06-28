"""Wipe everything from Cognee (graph, vector, relational, cache). Debug use only.

prune_data/prune_system can leave behind a zero-byte .shadow (WAL) file that
corrupts the Kuzu DB on the next open.  This script deletes the database
directory at the filesystem level first, which is the only reliable fix.
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load .env and env defaults before cognee touches any config.
from sentinel.connection import setup_cognee  # noqa: E402


def _find_cognee_db_dirs() -> list[Path]:
    """Return all cognee graph DB directories/files to delete."""
    import cognee
    from cognee.base_config import get_base_config
    from cognee.infrastructure.databases.graph.config import get_graph_config

    base_cfg = get_base_config()
    db_dir = Path(base_cfg.system_root_directory) / "databases"
    data_dir = Path(base_cfg.data_root_directory)

    targets: list[Path] = []
    if db_dir.exists():
        # Delete everything inside databases/ (graph DB + any shadow/WAL files).
        targets.append(db_dir)

    if data_dir.exists():
        targets.append(data_dir)

    return targets


def _wipe_filesystem() -> None:
    """Delete cognee's on-disk databases and data storage."""
    targets = _find_cognee_db_dirs()
    if not targets:
        print("   no database directories found — already clean")
        return
    for p in targets:
        print(f"   deleting {p} ...")
        shutil.rmtree(p, ignore_errors=True)
    print("   filesystem wipe done")


import asyncio  # noqa: E402


async def _wipe_relational() -> None:
    """Try cognee's prune for the relational (SQLite) metadata layer."""
    import cognee

    try:
        await cognee.prune.prune_data()
        await cognee.prune.prune_system(metadata=True)
        print("   cognee prune done")
    except Exception as exc:
        # Graph DB is already gone from the filesystem wipe; prune may fail.
        print(f"   cognee prune skipped ({type(exc).__name__}: {exc})")


async def main() -> None:
    await setup_cognee()

    print("=== Sentinel wipe ===")
    print("Step 1: filesystem-level delete (removes graph DB + any stale shadow files)")
    _wipe_filesystem()

    print("Step 2: cognee relational / metadata prune")
    await _wipe_relational()

    print("\nDone — run day3_flip.py to rebuild from scratch.")


if __name__ == "__main__":
    asyncio.run(main())
