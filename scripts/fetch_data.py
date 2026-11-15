"""Fetch the research datasets into data/raw (idempotent).

    python scripts/fetch_data.py

Sources:
  * NASA C-MAPSS turbofan degradation (NASA PCoE; Zenodo mirror of CMAPSSData.zip)
  * UCI AI4I 2020 predictive maintenance (UCI ML Repository, dataset 601)

The datasets are not redistributed in this repository. Respect their licences
and cite them when publishing results.
"""

from __future__ import annotations

import io
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

CMAPSS_URL = "https://zenodo.org/records/15346912/files/CMAPSSData.zip?download=1"
AI4I_URL = "https://archive.ics.uci.edu/static/public/601/ai4i+2020+predictive+maintenance+dataset.zip"


def download(url: str, destination: Path, timeout: int = 180) -> bytes:
    if destination.exists() and destination.stat().st_size > 0:
        print(f"cached: {destination.relative_to(ROOT)}")
        return destination.read_bytes()
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = response.read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    print(f"saved: {destination.relative_to(ROOT)} ({len(payload) / 1024:.0f} KB)")
    return payload


def extract(payload: bytes, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        archive.extractall(folder)
    print(f"extracted into {folder.relative_to(ROOT)}")


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)

    cmapss_zip = RAW / "cmapss.zip"
    extract(download(CMAPSS_URL, cmapss_zip), RAW / "cmapss")

    ai4i_zip = RAW / "ai4i.zip"
    extract(download(AI4I_URL, ai4i_zip), RAW / "ai4i")

    checks = {
        "C-MAPSS train_FD001": RAW / "cmapss" / "train_FD001.txt",
        "C-MAPSS test_FD001": RAW / "cmapss" / "test_FD001.txt",
        "C-MAPSS RUL_FD001": RAW / "cmapss" / "RUL_FD001.txt",
        "AI4I 2020": RAW / "ai4i" / "ai4i2020.csv",
    }
    missing = [label for label, path in checks.items() if not path.exists()]
    if missing:
        print(f"missing after extraction: {missing}", file=sys.stderr)
        return 1
    print("datasets ready. Next: python -m sentinel.pipelines.build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
