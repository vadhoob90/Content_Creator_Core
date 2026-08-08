"""Normalize source-distribution metadata for reproducible release archives."""

from __future__ import annotations

import argparse
import gzip
import os
import tarfile
import tempfile
from pathlib import Path


def normalize_sdist(path: Path, source_date_epoch: int) -> None:
    """Rewrite a source distribution with deterministic ownership and timestamps."""
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
        try:
            with (
                tarfile.open(path, mode="r:gz") as source,
                gzip.GzipFile(
                    filename="",
                    mode="wb",
                    compresslevel=9,
                    fileobj=temporary,
                    mtime=source_date_epoch,
                ) as compressed,
                tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as target,
            ):
                for member in source:
                    payload = source.extractfile(member) if member.isfile() else None
                    member.uid = 0
                    member.gid = 0
                    member.uname = ""
                    member.gname = ""
                    member.mtime = source_date_epoch
                    member.pax_headers = {}
                    target.addfile(member, payload)
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)


def main() -> None:
    """Normalize every source distribution supplied on the command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        source_date_epoch = int(os.environ["SOURCE_DATE_EPOCH"])
    except (KeyError, ValueError) as error:
        parser.error(f"SOURCE_DATE_EPOCH must be an integer: {error}")
    for archive in args.archives:
        normalize_sdist(archive, source_date_epoch)


if __name__ == "__main__":
    main()
