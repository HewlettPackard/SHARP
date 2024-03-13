#!/usr/bin/env python3
"""
Validate one or more workflow files in the CNCF workflow format.

Takes one or more filenames as command-line arguments
Uses the WorkflowValidator class to ensure they conform to the CNCF format.

© Copyright 2022--2024 Hewlett Packard Enterprise Development LP
"""

from serverlessworkflow.sdk.workflow import Workflow  # type: ignore
from serverlessworkflow.sdk.workflow_validator import WorkflowValidator  # type: ignore
import sys

assert len(sys.argv) > 1  # Need at least one argument: filename(s) to validate
with open(sys.argv[1]) as f:
    wf = Workflow.from_source(f.read())
    WorkflowValidator(wf).validate()
