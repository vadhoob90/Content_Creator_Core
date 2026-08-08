import io
import runpy
import tarfile
from pathlib import Path

NORMALIZE_SDIST = runpy.run_path(str(Path(__file__).parents[1] / "scripts" / "normalize_sdist.py"))[
    "normalize_sdist"
]


def _source_distribution(path: Path, *, mtime: int, owner: str) -> None:
    payload = b"release evidence\n"
    member = tarfile.TarInfo("content_creator-1.6.0/evidence.txt")
    member.size = len(payload)
    member.mtime = mtime
    member.uid = mtime
    member.gid = mtime
    member.uname = owner
    member.gname = owner
    with tarfile.open(path, mode="w:gz") as archive:
        archive.addfile(member, io.BytesIO(payload))


def test_sdist_normalization_produces_byte_identical_archives(tmp_path: Path) -> None:
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    _source_distribution(first, mtime=100, owner="first")
    _source_distribution(second, mtime=200, owner="second")

    NORMALIZE_SDIST(first, source_date_epoch=42)
    NORMALIZE_SDIST(second, source_date_epoch=42)

    assert first.read_bytes() == second.read_bytes()
    with tarfile.open(first, mode="r:gz") as archive:
        member = archive.getmembers()[0]
    assert (member.mtime, member.uid, member.gid) == (42, 0, 0)
    assert (member.uname, member.gname) == ("", "")
