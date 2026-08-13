"""End-to-end pipeline: download → ETL → load → validate → readout."""

from __future__ import annotations

import argparse

from analytics.config import EXPERIMENT
from analytics.download_data import run as download
from analytics.etl_listings import run as etl
from analytics.load_database import run as load
from analytics.logging_config import get_logger
from analytics.run_analysis import main as readout

log = get_logger(__name__)


def run(*, force_download: bool = False, skip_calendar: bool = False,
        skip_download: bool = False, skip_etl: bool = False) -> None:
    if not skip_download:
        download(force=force_download)
    if not skip_etl:
        etl(skip_calendar=skip_calendar)
    counts = load()
    log.info("pipeline complete", extra=counts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the StayLab data pipeline")
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-etl", action="store_true")
    parser.add_argument("--skip-calendar", action="store_true")
    parser.add_argument("--readout", action="store_true",
                        help="print the experiment readout after loading")
    args = parser.parse_args()
    run(
        force_download=args.force_download,
        skip_calendar=args.skip_calendar,
        skip_download=args.skip_download,
        skip_etl=args.skip_etl,
    )
    if args.readout:
        log.info("printing readout", extra={"experiment": EXPERIMENT.experiment_key})
        readout()


if __name__ == "__main__":
    main()
