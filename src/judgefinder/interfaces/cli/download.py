from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Sequence
from pathlib import Path

from judgefinder.adapters.attachments.downloader import download_notice_attachments


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download HWP/HWPX/PDF attachments without collector configuration or DB."
    )
    parser.add_argument("urls", nargs="*", help="Notice detail page URLs.")
    parser.add_argument(
        "--urls-file", type=Path, help="UTF-8 text file with one notice URL per line."
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/attachments"))
    parser.add_argument("--timeout", type=float, default=30.0, help="Request timeout in seconds.")
    parser.add_argument("--max-size-mb", type=int, default=50, help="Maximum size per attachment.")
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0 or args.max_size_mb <= 0:
        parser.error("--timeout and --max-size-mb must be positive finite values.")
    urls: list[str] = list(args.urls)
    if args.urls_file is not None:
        try:
            lines = args.urls_file.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError) as exc:
            parser.error(f"Cannot read URL file: {exc}")
        urls.extend(
            line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")
        )
    urls = list(dict.fromkeys(url.strip() for url in urls if url.strip()))
    if not urls:
        parser.error("Provide at least one notice URL or --urls-file.")

    failed = False
    for url in urls:
        try:
            report = download_notice_attachments(
                url,
                output_dir=args.output_dir,
                timeout_seconds=args.timeout,
                max_file_bytes=args.max_size_mb * 1024 * 1024,
            )
        except (ValueError, OSError) as exc:
            print(f"ERROR {url}: {exc}", file=sys.stderr)
            failed = True
            continue
        for attachment in report.files:
            print(report.directory / attachment.filename)
        for failure in report.failures:
            print(f"ERROR {failure.url}: {failure.reason}", file=sys.stderr)
        for reason in report.unsupported:
            print(f"UNSUPPORTED {url}: {reason}", file=sys.stderr)
        print(f"Manifest: {report.directory / 'manifest.json'}", file=sys.stderr)
        failed = failed or not report.ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
