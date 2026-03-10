#!/usr/bin/env python3
"""
SHARP workflow execution - run multiple experiments in sequence.

Current implementation: simple sequential workflow execution.
Future: DAG workflows with dependencies and parallelism.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import sys
from pathlib import Path
from typing import Optional, Union

import yaml

from src.core.config.schema import WorkflowConfig


def load_workflow_from_dict(workflow_data: dict) -> WorkflowConfig:
    """
    Load workflow configuration from dictionary.

    Args:
        workflow_data: Workflow configuration dictionary

    Returns:
        WorkflowConfig instance

    Raises:
        ValueError: If workflow data is invalid
    """
    if not workflow_data:
        raise ValueError("Empty workflow configuration")

    # Validate against schema
    try:
        config = WorkflowConfig(**workflow_data)
        # Warn about unsupported Phase 6+ features
        if hasattr(config, '__pydantic_extra__') and config.__pydantic_extra__:
            for key in config.__pydantic_extra__.keys():
                if key in ['steps', 'parallel_groups', 'depends_on']:
                    print(f"⚠ Warning: '{key}' is not yet supported (Phase 6+ feature)", file=sys.stderr)
        return config
    except Exception as e:
        raise ValueError(f"Invalid workflow configuration: {e}")


def load_workflow(workflow_path: str) -> WorkflowConfig:
    """
    Load workflow configuration from YAML file.

    Args:
        workflow_path: Path to workflow YAML file

    Returns:
        WorkflowConfig instance

    Raises:
        FileNotFoundError: If workflow file doesn't exist
        ValueError: If workflow YAML is invalid
    """
    workflow_file = Path(workflow_path)
    if not workflow_file.exists():
        raise FileNotFoundError(f"Workflow file not found: {workflow_path}")

    with open(workflow_file, 'r') as f:
        data = yaml.safe_load(f)

    return load_workflow_from_dict(data)


def run_workflow(
    workflow: Union[str, dict, WorkflowConfig],
    verbose: bool = False,
    base_dir: Optional[Path] = None
) -> int:
    """
    Execute workflow experiments sequentially.

    Current implementation: runs each experiment in order, stopping on first failure.
    No dependencies, no parallelism, no state passing between experiments.

    Args:
        workflow: Workflow specification as:
                  - str: Path to workflow YAML file
                  - dict: Workflow configuration dictionary
                  - WorkflowConfig: Already-validated workflow config
        verbose: Whether to print progress information
        base_dir: Base directory for resolving relative task paths.
                  If None and workflow is a file path, uses the file's directory.
                  If None and workflow is dict/WorkflowConfig, uses current directory.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    # Load/validate workflow configuration
    try:
        if isinstance(workflow, str):
            workflow_config = load_workflow(workflow)
            # Default base_dir to workflow file's directory
            if base_dir is None:
                base_dir = Path(workflow).parent
        elif isinstance(workflow, dict):
            workflow_config = load_workflow_from_dict(workflow)
            # Default base_dir to current directory for dict input
            if base_dir is None:
                base_dir = Path.cwd()
        elif isinstance(workflow, WorkflowConfig):
            workflow_config = workflow
            # Default base_dir to current directory for WorkflowConfig input
            if base_dir is None:
                base_dir = Path.cwd()
        else:
            raise ValueError(f"Invalid workflow type: {type(workflow)}")
    except (FileNotFoundError, ValueError) as e:
        print(f"\n✗ Error loading workflow: {e}", file=sys.stderr)
        return 1

    if verbose:
        # Use workflow description or "workflow" as default name
        workflow_name = workflow_config.description
        if not workflow_name and isinstance(workflow, str):
            workflow_name = Path(workflow).stem
        print(f"\nExecuting workflow: {workflow_name or 'workflow'}")
        if workflow_config.experiment:
            print(f"Experiment name: {workflow_config.experiment}")
        print(f"Tasks: {len(workflow_config.workflow)}\n")

    # Import launch module for running individual experiments
    from src.cli import launch

    # Resolve task paths relative to base directory
    workflow_dir = base_dir

    failed_tasks = []
    for i, workflow_task in enumerate(workflow_config.workflow, start=1):
        task_data = {}
        task_identifier = None
        resolved_path = None

        # Step 1: Load base configuration from file if specified
        if workflow_task.include:
            task_path = workflow_task.include
            task_identifier = task_path

            # Resolve task path
            if not Path(task_path).is_absolute():
                resolved_path = workflow_dir / task_path
            else:
                resolved_path = Path(task_path)

            if not resolved_path.exists():
                print(f"\n✗ Error: Task file not found: {task_path}", file=sys.stderr)
                failed_tasks.append((task_identifier, "file not found"))
                # Stop on first failure (sequential workflow behavior)
                break

            # Load task config from file (base configuration)
            try:
                with open(resolved_path, 'r') as f:
                    task_data = yaml.safe_load(f) or {}
            except Exception as e:
                print(f"\n✗ Error loading task {task_path}: {e}", file=sys.stderr)
                failed_tasks.append((task_identifier, f"load error: {e}"))
                # Stop on first failure (sequential workflow behavior)
                break

        # Step 2: Override/merge with inline fields (composition)
        # This allows hybrid: include a file + override specific fields

        # Override task name if specified inline
        if workflow_task.task is not None:
            if 'options' not in task_data:
                task_data['options'] = {}
            task_data['options']['task'] = workflow_task.task
            task_identifier = f"task {i} ({workflow_task.task})"

        # Override backends if specified inline
        if workflow_task.backends is not None:
            task_data['backends'] = workflow_task.backends

        # Merge options (inline values take precedence)
        if workflow_task.options is not None:
            if 'options' not in task_data:
                task_data['options'] = {}
            task_data['options'].update(workflow_task.options)

        # Set identifier if not already set (pure inline case)
        if task_identifier is None:
            task_identifier = f"task {i} ({workflow_task.task})"

        # Display what we're running
        if verbose:
            if workflow_task.include and workflow_task.task:
                print(f"[{i}/{len(workflow_config.workflow)}] Running: {workflow_task.include} (task: {workflow_task.task})")
            elif workflow_task.include:
                print(f"[{i}/{len(workflow_config.workflow)}] Running: {workflow_task.include}")
            else:
                print(f"[{i}/{len(workflow_config.workflow)}] Running: {workflow_task.task}")

        # Build argv for launch.main()
        task_argv = []

        # For file includes: add -f flag and optional task name
        if workflow_task.include:
            # If task file specifies a task name in options, pass it as positional argument
            task_name = None
            if task_data and 'options' in task_data and 'task' in task_data['options']:
                task_name = task_data['options']['task']

            # Add task name if found
            if task_name:
                task_argv.append(task_name)

            # Add experiment name from workflow config if provided
            # (task config file's experiment field takes precedence in launch.py)
            if workflow_config.experiment:
                task_argv.extend(['-e', workflow_config.experiment])

            # Add the file path
            task_argv.extend(['-f', str(resolved_path)])

        # For inline tasks: build full argv from task definition
        else:
            # Add task name (required for inline tasks)
            task_argv.append(workflow_task.task)

            # Add backends
            if workflow_task.backends:
                for backend in workflow_task.backends:
                    task_argv.extend(['-b', backend])

            # Add options as JSON
            if workflow_task.options:
                import json
                task_argv.extend(['-j', json.dumps(workflow_task.options)])

            # Add experiment name from workflow config if provided
            # (task options.experiment takes precedence in launch.py)
            if workflow_config.experiment:
                task_argv.extend(['-e', workflow_config.experiment])

        # Add verbose flag if needed
        if verbose:
            task_argv.append('--verbose')

        # Run task
        exit_code = launch.main(task_argv)

        if exit_code != 0:
            print(f"\n✗ Task failed: {task_identifier} (exit code: {exit_code})", file=sys.stderr)
            failed_tasks.append((task_identifier, f"exit code {exit_code}"))
            # Stop on first failure (sequential workflow behavior)
            break

        if verbose:
            print(f"✓ Completed: {task_identifier}\n")

    # Print summary
    if failed_tasks:
        print(f"\n✗ Workflow failed: {len(failed_tasks)} task(s) failed", file=sys.stderr)
        for task_identifier, reason in failed_tasks:
            print(f"  - {task_identifier}: {reason}", file=sys.stderr)
        return 1

    if verbose:
        print(f"\n✓ Workflow completed successfully: {len(workflow_config.workflow)} tasks")

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """
    Main entry point for workflow command.

    Args:
        argv: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Execute SHARP workflow (sequential tasks)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  workflow experiments/scaling_study.yaml
  workflow --verbose experiments/matrix_suite.yaml

Workflow YAML Format (file includes):
  version: 1.0.0
  description: Optional description
  experiment: optional_experiment_name  # For runlogs/ subdirectory
  workflow:
    - include: task1.yaml
    - include: task2.yaml
    - include: task3.yaml

Workflow YAML Format (inline tasks):
  version: 1.0.0
  workflow:
    - task: sleep
      backends: [local]
      options:
        repeater: COUNT
        repeats: 5
    - task: matmul
      backends: [local, perf]
      options:
        repeater: RSE
        threshold: 0.05

Mixed format (file includes + inline):
  version: 1.0.0
  workflow:
    - include: baseline.yaml
    - task: optimized_version
      backends: [local]
      options: {repeater: COUNT, repeats: 10}
        """
    )

    parser.add_argument(
        'workflow',
        help='Path to workflow YAML file'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print progress information'
    )

    args = parser.parse_args(argv)

    # When called from CLI, always pass file path (string)
    return run_workflow(args.workflow, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
