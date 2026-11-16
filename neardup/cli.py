"""Command line entry point.

Usage: python -m neardup.cli --dir demo/corpus --out out/report.json

Every non-empty line of every *.txt file under --dir (files processed in
sorted name order) is treated as one record, so a corpus directory does
not need one file per record.
"""

import argparse
import hashlib
import json
from pathlib import Path

from .matcher import DEFAULT_THRESHOLD
from .report import build_report


def iter_records(directory):
    record_id = 0
    for path in sorted(Path(directory).glob("*.txt")):
        with path.open("r", encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, 1):
                text = line.rstrip("\n")
                if not text.strip():
                    continue
                yield {
                    "id": record_id,
                    "source": f"{path.name}:{lineno}",
                    "text": text,
                    "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                }
                record_id += 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="neardup", description=__doc__)
    parser.add_argument("--dir", required=True, help="corpus directory containing *.txt files")
    parser.add_argument("--out", required=True, help="path to write the JSON report")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help="max Hamming distance for near-duplicates (default: 3)")
    args = parser.parse_args(argv)

    records = list(iter_records(args.dir))
    report = build_report(records, threshold=args.threshold)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)

    print(
        f"processed={report['processed']} "
        f"near_duplicate_groups={len(report['groups'])} "
        f"buckets={report['buckets']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
