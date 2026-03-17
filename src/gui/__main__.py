"""
Entry point for SHARP GUI from command line.

Starts the Shiny application with appropriate settings.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from shiny import run_app
from ..core.config.settings import Settings


def main() -> None:
    """Launch the SHARP GUI with settings from settings.yaml."""
    settings = Settings()

    # Run the app with reload for development
    run_app(  # type: ignore
        "src.gui.app:app",
        host=settings.get("gui.host", "0.0.0.0"),
        port=settings.get("gui.port", 8000),
        reload=True
    )


if __name__ == "__main__":
    main()
