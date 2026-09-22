# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Entry point for the SHARP GUI (uv run gui)."""

import argparse
import sys

import uvicorn

from ..core.config.settings import Settings


def main(argv: list[str] | None = None) -> None:
    """Launch the SHARP GUI using configured host and port.

    CLI flags override settings.yaml values:
      --host HOST   Bind address (default: gui.host from settings, 0.0.0.0)
      --port PORT   HTTP port   (default: gui.port from settings, 8282)
      --no-reload   Disable auto-reload on source changes
    """
    settings = Settings()

    parser = argparse.ArgumentParser(
        prog="gui",
        description="Launch the SHARP GUI.",
    )
    parser.add_argument(
        "--host",
        default=settings.get("gui.host", "0.0.0.0"),
        help="Bind address (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.get("gui.port", 8282),
        help="HTTP port (default: %(default)s)",
    )
    parser.add_argument(
        "--no-reload",
        dest="reload",
        action="store_false",
        default=True,
        help="Disable auto-reload on source changes",
    )

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    uvicorn.run(
        "src.gui.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=["src"] if args.reload else None,
    )


if __name__ == "__main__":
    main()