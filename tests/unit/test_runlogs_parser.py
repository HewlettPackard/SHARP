import json
import textwrap
from pathlib import Path

from src.core.runlogs.parser import extract_runtime_options_from_markdown


def _write_markdown(tmp_path: Path, header_text: str) -> Path:
    runtime_payload = {
        "entry_point": "/bin/echo",
        "args": ["hello"],
        "task": "echo",
        "backend_names": ["local"],
        "repeats": 2,
    }
    invariants_payload = {
        "launch_id": {
            "type": "string",
            "description": "Unique launch identifier",
            "values": {"abcd1234": "abcd1234"},
        }
    }

    markdown = textwrap.dedent(
        f"""
        Experiment completed at 2025-01-01 (total experiment time: 10s, total rows: 2).

        ## {header_text}

        ```json
        {json.dumps(runtime_payload, indent=2)}
        ```

        ## Invariant parameters

        Parameters are listed by name, with values keyed by launch ID.

        ```json
        {json.dumps(invariants_payload, indent=2)}
        ```
        """
    ).strip()

    md_path = tmp_path / f"sample_{header_text.replace(' ', '_')}.md"
    md_path.write_text(markdown)
    return md_path


def test_extract_runtime_options_handles_legacy_header(tmp_path):
    md_path = _write_markdown(tmp_path, "Runtime options")

    runtime_opts = extract_runtime_options_from_markdown(md_path)

    assert runtime_opts["entry_point"] == "/bin/echo"
    assert runtime_opts["args"] == ["hello"]
    assert runtime_opts["backend_names"] == ["local"]
    assert runtime_opts["repeats"] == 2


def test_extract_runtime_options_handles_starting_header(tmp_path):
    md_path = _write_markdown(tmp_path, "Starting runtime options")

    runtime_opts = extract_runtime_options_from_markdown(md_path)

    assert runtime_opts["entry_point"] == "/bin/echo"
    assert runtime_opts["args"] == ["hello"]
    assert runtime_opts["backend_names"] == ["local"]
    assert runtime_opts["repeats"] == 2
