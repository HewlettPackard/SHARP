"""
Logger class to record all the information about a task run in CSV.

A task's run record (line in a CSV file) has two groups of fields:
  - column fields, shared and repeated across all copies (rows) of the task.
  - Per-run data (primarily performance) for each copy (row) of the task.
CSV logs are identified by experiment (directory name) and task (filename)

In addition to the CSV file, a markdown file is created with additional
metadata on the task run, as well as field descriptions for the CSV log.

© Copyright 2022--2024 Hewlett Packard Enterprise Development LP
"""

import csv
from datetime import datetime, timezone
import os
import platform
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

        mydir = os.path.join(topdir, options["experiment"])
        if not os.path.exists(mydir):
            os.makedirs(mydir)

        self.__basefn: str = os.path.join(mydir, self.__task.split("/")[-1])
        if options["verbose"]:
            print(f"Logging runs to: {self.__basefn}")

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

        self.__preamble += "\n## Runtime options:\n\n"
        for key in options.keys():
            if key not in ["metrics"]:
                self.__preamble += f"{key}:\t{options[key]}\n"

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
        ), f"Can't add a new field {field} that isn't in previous row"
        if len(self.__rows) == 0 or field in self.__rows[-1]:
            self.__rows.append({})
        self.__rows[-1][field] = value

    #################
    def save_data(self, mode: str, sys_specs: Dict[str, Any]) -> None:
        """
        Save data before termination.

        When the class is no longer in use, or when we need to start a new set
        of rows with the same columns, save all pending data to the output files.
        (Don't use __del__(), since the order of cleanup is indeterminate.)

        Args:
            mode (str): the write mode on the file: truncate ("w") or append ("a")
            sys_specs (Dict): Specs of system under test
        """
        self.__save_csv(mode)
        if mode == "w":
            self.__save_md(mode, sys_specs)

    #################
    def __save_csv(self, mode: str) -> None:
        """
        Save all the key/value pairs (including header data) to the CSV file.

        Args:
            mode (str): the write mode on the file: truncate ("w") or append ("a")
        """
        assert len(self.__rows) > 0, "There's nor row data to save"
        records = [{**self.__columns, **r} for r in self.__rows]
        fnames = list(self.__columns.keys()) + list(self.__rows[0].keys())

        with open(self.__basefn + ".csv", mode, encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fnames)
            if mode == "w":
                writer.writeheader()
            writer.writerows(records)

    #################
    def __save_md(self, mode: str, sys_specs: Dict[str, Any]) -> None:
        """
        Save all the metadata to the .md file.

        Args:
            mode: the write mode on the file: truncate ("w") or append ("a")
            sys_specs (Dict): Specs of system under test
        """
        with open(self.__basefn + ".md", mode, encoding="utf-8") as f:
            now = datetime.now(timezone.utc)
            f.write(f"Experiment completed at {now}\n\n")
            f.write(self.__preamble)
            f.write("\n\n## Field description\n\n")

            for field in self.__metadata.keys():
                f.write("  * `" + field + "` ")
                f.write("(" + self.__metadata[field]["type"] + "): ")
                f.write(self.__metadata[field]["desc"] + ".\n")

            if sys_specs:
                f.write("\n## System configuration:\n\n")
                for key in sys_specs:
                    f.write(f"### {key}\n{sys_specs[key]}\n")
