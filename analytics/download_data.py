"""Fetch the Inside Airbnb snapshot into data/raw (idempotent)."""

from __future__ import annotations

import argparse

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from analytics.config import SOURCE
from analytics.logging_config import get_logger

log = get_logger(__name__)

# Inside Airbnb's CDN rejects requests without a browser-like User-Agent.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def _download(url: str, dest) -> int:
    total = 0
    with httpx.stream("GET", url, headers=HEADERS, timeout=120.0,
                      follow_redirects=True) as response:
        response.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with tmp.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 20):
                handle.write(chunk)
                total += len(chunk)
        tmp.replace(dest)
    return total


def run(force: bool = False) -> None:
    SOURCE.raw_dir.mkdir(parents=True, exist_ok=True)
    for filename, url in SOURCE.files.items():
        dest = SOURCE.raw_dir / filename
        if dest.exists() and not force:
            log.info("already present", extra={"file": filename,
                                               "bytes": dest.stat().st_size})
            continue
        log.info("downloading", extra={"file": filename, "url": url})
        size = _download(url, dest)
        log.info("downloaded", extra={"file": filename, "bytes": size})


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Inside Airbnb source files")
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    args = parser.parse_args()
    run(force=args.force)
    log.info("snapshot ready", extra={"city": SOURCE.city, "snapshot": SOURCE.snapshot})


if __name__ == "__main__":
    main()
