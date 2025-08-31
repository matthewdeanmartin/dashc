from __future__ import annotations

import argparse
import logging
import logging.config
import sys
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

import argcomplete

# Local imports
from dashc import __about__
from dashc.custom_exceptions import DashCException
from dashc.single_file import dashc as build_single_file
from dashc.single_module import dashc_module as build_module
from dashc.utils.cli_suggestions import SmartParser


# -----------------------------
# Exit codes (bash-friendly)
# -----------------------------
class ExitCode(IntEnum):
    OK = 0
    BAD_USAGE = 2
    CONFIG = 10
    RUNTIME = 1
    INTERRUPTED = 130


# -----------------------------
# Logging config helper
# -----------------------------


def _generate_logging_config(level: str = "INFO") -> dict:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "std": {
                "format": "%(levelname)s: %(message)s",
            }
        },
        "handlers": {
            "stderr": {
                "class": "logging.StreamHandler",
                "level": level,
                "formatter": "std",
                "stream": "ext://sys.stderr",
            }
        },
        "root": {"handlers": ["stderr"], "level": level},
    }


# -----------------------------
# Dataclasses for shared options
# -----------------------------
@dataclass
class GlobalOpts:
    verbose: bool
    quiet: bool
    dry_run: bool


# -----------------------------
# Handlers
# -----------------------------


def _resolve_shebang(one_line: bool, shebang: str | None) -> str | None:
    return None if one_line else (shebang or "/usr/bin/env bash")


def handle_file(args: argparse.Namespace, g: GlobalOpts) -> int:
    src = Path(args.path)
    if not src.is_file():
        logging.error("Input file does not exist: %s", src)
        return int(ExitCode.CONFIG)

    try:
        script_or_cmd = build_single_file(
            source_path=src,
            plain_text=args.plain_text,
            shebang=_resolve_shebang(args.one_line, args.shebang),
        )
    except DashCException as e:
        logging.error(str(e))
        return int(ExitCode.RUNTIME)

    if args.out:
        out_path = Path(args.out)
        if g.dry_run:
            logging.info("DRY-RUN: would write script to %s", out_path)
        else:
            out_path.write_text(script_or_cmd, encoding="utf-8")
            out_path.chmod(0o755)
            logging.info("Wrote script to %s", out_path)
    else:
        # Print to STDOUT (so users can pipe into bash if they want)
        print(script_or_cmd)
    return int(ExitCode.OK)


def handle_module(args: argparse.Namespace, g: GlobalOpts) -> int:
    src_dir = Path(args.dir)
    if not src_dir.is_dir():
        logging.error("Input directory does not exist: %s", src_dir)
        return int(ExitCode.CONFIG)

    try:
        script_or_cmd = build_module(
            src_dir=src_dir,
            entrypoint=args.entrypoint,
            shebang=_resolve_shebang(args.one_line, args.shebang),
            zip_compression=args.zip_compression,
            zip_compresslevel=args.zip_compresslevel,
        )
    except DashCException as e:
        logging.error(str(e))
        return int(ExitCode.RUNTIME)
    except ValueError as e:
        logging.error(str(e))
        return int(ExitCode.BAD_USAGE)

    if args.out:
        out_path = Path(args.out)
        if g.dry_run:
            logging.info("DRY-RUN: would write script to %s", out_path)
        else:
            out_path.write_text(script_or_cmd, encoding="utf-8")
            out_path.chmod(0o755)
            logging.info("Wrote script to %s", out_path)
    else:
        print(script_or_cmd)
    return int(ExitCode.OK)


# -----------------------------
# Parser wiring
# -----------------------------


def add_common_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    p.add_argument("-q", "--quiet", action="store_true", help="Silence non-error logs")
    p.add_argument("--dry-run", action="store_true", help="Do not write files; describe what would happen")


def build_parser() -> SmartParser:
    parser = SmartParser(
        prog=__about__.__title__,
        description=__about__.__description__,
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {__about__.__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    # file
    p_file = sub.add_parser(
        "file",
        help="Build a bash script or one-line command from a single Python file",
        description=(
            "Compile one Python source file into a bash script that runs it via `python -c`,\n"
            "optionally embedding compressed source."
        ),
    )
    p_file.add_argument("path", help="Path to a Python source file")
    p_file.add_argument("-o", "--out", help="Write output to this path; prints to STDOUT if omitted")
    p_file.add_argument("--plain-text", action="store_true", help="Embed source as plain text (no compression)")
    p_file.add_argument("--shebang", default="/usr/bin/env bash", help="Shebang line for script output")
    p_file.add_argument("--one-line", action="store_true", help="Output a one-line command instead of a script")
    add_common_flags(p_file)
    p_file.set_defaults(func=handle_file)

    # module
    p_mod = sub.add_parser(
        "module",
        help="Package a directory (package/app) and run a module/function",
        description=(
            "Zip a Python package/app directory in-memory and generate a script that either runs a module\n"
            "(like `python -m pkg`) or imports a function (like `pkg.cli:main`)."
        ),
    )
    p_mod.add_argument("dir", help="Path to the source directory (package root)")
    p_mod.add_argument(
        "--entrypoint",
        help="Module or module:function to run. If omitted, auto-detect a package with __main__.py",
    )
    p_mod.add_argument(
        "--zip-compression",
        choices=["stored", "deflated", "bzip2", "lzma"],
        default="deflated",
        help="Compression method for embedded zip",
    )
    p_mod.add_argument("--zip-compresslevel", type=int, help="Compression level (varies by method)")
    p_mod.add_argument("-o", "--out", help="Write output to this path; prints to STDOUT if omitted")
    p_mod.add_argument("--shebang", default="/usr/bin/env bash", help="Shebang line for script output")
    p_mod.add_argument("--one-line", action="store_true", help="Output a one-line command instead of a script")
    add_common_flags(p_mod)
    p_mod.set_defaults(func=handle_module)

    return parser


# -----------------------------
# Main entry point
# -----------------------------


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argcomplete.autocomplete(parser)

    args = parser.parse_args(argv)

    # logging level
    if getattr(args, "verbose", False):
        level = "DEBUG"
    elif getattr(args, "quiet", False):
        level = "CRITICAL"
    else:
        level = "INFO"
    logging.config.dictConfig(_generate_logging_config(level=level))

    g = GlobalOpts(verbose=args.verbose, quiet=args.quiet, dry_run=getattr(args, "dry_run", False))

    try:
        rc = args.func(args, g)  # type: ignore[arg-type]
        return int(rc)
    except DashCException as e:
        logging.error(str(e))
        return int(ExitCode.RUNTIME)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return int(ExitCode.INTERRUPTED)
    except SystemExit as e:
        # Let argparse/SystemExit codes flow through (e.g., --help)
        try:
            return int(e.code)  # type: ignore[arg-type]
        except Exception:
            return int(ExitCode.BAD_USAGE)
    except Exception as e:  # pragma: no cover - unexpected bug
        logging.exception("unexpected error: %s", e)
        return int(ExitCode.RUNTIME)


if __name__ == "__main__":
    sys.exit(main())
