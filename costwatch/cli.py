"""Command line entry: python -m costwatch.cli run | ask "question" """
import argparse
import logging
import sys
from dataclasses import replace

from .config import Config
from .pipeline import run, write_outputs


def main(argv=None):
    p = argparse.ArgumentParser(prog="costwatch")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="analyse shipments and write the output CSV")
    r.add_argument("--shipments"); r.add_argument("--notes"); r.add_argument("--output")
    a = sub.add_parser("ask", help="ask a plain-English question about the findings")
    a.add_argument("question"); a.add_argument("--output")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = Config()
    from pathlib import Path
    overrides = {}
    if getattr(args, "shipments", None): overrides["shipments_path"] = Path(args.shipments)
    if getattr(args, "notes", None): overrides["notes_path"] = Path(args.notes)
    if getattr(args, "output", None): overrides["output_path"] = Path(args.output)
    cfg = replace(cfg, **overrides)

    if args.cmd == "run":
        df = run(cfg)
        write_outputs(df, cfg)
        print(f"{len(df)} rows written to {cfg.output_path} "
              f"({(df.flagged == 'Yes').sum()} flagged, {(df.flagged != 'Yes').sum()} justified)")
    else:
        from .ask import answer
        print(answer(args.question, cfg.output_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
