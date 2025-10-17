"""
Logger class to record all the information about a task run in CSV.

A task's run record (line in a CSV file) has two groups of fields:
  - column fields, shared and repeated across all copies (rows) of the task.
  - Per-run data (primarily performance) for each rank (row) of the task.
CSV logs are identified by experiment (directory name) and task (filename)

In addition to the CSV file, a markdown file is created with additional
metadata on the task run, as well as field descriptions for the CSV log.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

import csv
from datetime import datetime, timezone
import json
import os
import platform
import time
from typing import *
import subprocess


class Logger:
    """Implementation of a class to hold and record log data in CSV format."""

    #################
    def __init__(self, topdir: str, task: str, options: Dict[str, Any]):
        """
        Initialize Logger.

        Args:
            topdir (str): Full path of the top-level directory for logs
            experiment (str): The subdirectory for this experiment
            task (str): Base filename for CSV and md files
            options (dictionary): All experiment options
        """
        self.clear_rows()
        self.__columns: Dict[str, str] = {}
        self.__metadata: Dict[str, Dict[str, str]] = {}
        self.__task: str = task
        self.__start_time: float = time.perf_counter()

        mydir = os.path.join(topdir, options["experiment"])
        if not os.path.exists(mydir):
            os.makedirs(mydir)

        self.__basefn: str = os.path.join(mydir, self.__task.split("/")[-1])
        if options["verbose"]:
            print(f"Logging runs to: {self.__basefn} at time {self.__start_time}")

        # Prep text to go in the beginning of the markdown file:
        git = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
        )

        now: datetime = datetime.now(timezone.utc)
        self.__preamble: str = f"""\
This file describes the fields in the file {task}.csv. \
The measurements were run on {platform.node()}, starting at {now} (UTC).\n"""

        if git.returncode == 0:
            self.__preamble += f"The source code version used was from git hash: {git.stdout.strip()}\n"

        self.__preamble += "\n## Runtime options\n\n```json\n"
        # Exclude sys_spec_commands from runtime options output (it's shown in System configuration)
        options_filtered = {k: v for k, v in options.items() if k != "sys_spec_commands"}
        self.__preamble += json.dumps(options_filtered, indent=2)
        self.__preamble += "\n```"

    #################
    def clear_rows(self) -> None:
        """
        Clear all row data.

        Can be used externally to reset row data and keep columns.
        """
        self.__rows: List[Dict[str, Any]] = []

    #################
    def add_column(self, field: str, value: str, typ: str, desc: str) -> None:
        """
        Record metadata about a given field.

        Args:
            field (str): key for the column
            value (str): value for the entire column
            typ (str): type of value (for documdntation in metadata file)
            desc (str): description value (for documdntation in metadata file)
        """
        if field not in self.__metadata:
            self.__metadata[field] = {"type": typ, "desc": desc}
        self.__columns[field] = value

    #################
    def add_row_data(
        self, field: str, value: Union[str, int, float], typ: str, desc: str
    ) -> None:
        """
        Record a key/value pair of information specific to a row.

        Will add column to an existing row if that key doesn't exist there yet.

        Args:
            field (str): key for the column
            value (union): value for the entire column
            typ (str): type of value (for documdntation in metadata file)
            desc (str): description value (for documdntation in metadata file)
        """
        if field not in self.__metadata:
            self.__metadata[field] = {"type": typ, "desc": desc}

        assert (
            len(self.__rows) <= 1 or field in self.__rows[-2]
        ), f"Can't add a new field '{field}' that isn't in previous row"
        if len(self.__rows) == 0 or field in self.__rows[-1]:
            self.__rows.append({})
        self.__rows[-1][field] = value


    #################
    def save_csv(self, mode: str) -> None:
        """
        Save all the key/value pairs (including header data) to the CSV file.

        Args:
            mode (str): the write mode on the file: truncate ("w") or append ("a")
        """
        assert len(self.__rows) > 0, "There's nor row data to save"
        records = [{**self.__columns, **r} for r in self.__rows]
        fnames = list(self.__columns.keys()) + list(self.__rows[0].keys())
        fn: str = self.__basefn + ".csv"

        with open(fn, mode, encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fnames)
            if mode == "w" or os.path.getsize(fn) == 0:
                writer.writeheader()
            writer.writerows(records)

    #################
    def save_md(self, mode: str, sys_specs: Dict[str, Any]) -> None:
        """
        Save all the metadata to the .md file.

        Skips writing file if in append mode and it already exists
        Args:
            mode: the write mode on the file: truncate ("w") or append ("a")
            sys_specs (Dict): Specs of system under test
        """
        if mode == "a" and os.path.exists(self.__basefn + ".md"):
            return

        with open(self.__basefn + ".md", mode, encoding="utf-8") as f:
            now = datetime.now(timezone.utc)
            f.write(f"Experiment completed at {now} (total experiment time: ")
            f.write(f"{int(time.perf_counter() - self.__start_time)}s).\n\n")
            f.write(self.__preamble)
            f.write("\n\n## Field description\n\n")

            for field in self.__metadata.keys():
                f.write("  * `" + field + "` ")
                f.write("(" + self.__metadata[field]["type"] + "): ")
                f.write(self.__metadata[field]["desc"] + ".\n")

            if sys_specs:
                f.write("\n## System configuration\n\n")
                # Output as JSON for two-level structured data
                f.write("```json\n")
                f.write(json.dumps(sys_specs, indent=2))
                f.write("\n```\n")
