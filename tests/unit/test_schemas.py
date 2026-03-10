"""
Unit tests for Pydantic configuration schemas.

Tests validate schema structure, field validation, and error handling
for ExperimentConfig, BackendConfig, BenchmarkConfig, and related models.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
from pydantic import ValidationError

from src.core.config.schema import (
    ExperimentConfig,
    BackendConfig,
    BackendOptionConfig,
    BenchmarkConfig,
    BenchmarkSource,
    BenchmarkBuild,
    BenchmarkEntry,
    MetricDefinition,
    WorkflowConfig,
    WorkflowStep,
)


# ========== MetricDefinition Tests ==========

def test_metric_definition_defaults():
    """Metric definition applies correct default values."""
    metric = MetricDefinition(
        description="Test metric",
        extract="grep test | awk '{print $1}'"
    )
    assert metric.lower_is_better is True, "Default lower_is_better should be True"
    assert metric.type == 'numeric', "Default type should be 'numeric'"
    assert metric.units is None, "Default units should be None"


def test_metric_definition_type_validation():
    """Metric type must be 'numeric' or 'string'."""
    # Valid types
    MetricDefinition(description="Test", extract="grep test", type='numeric')
    MetricDefinition(description="Test", extract="grep test", type='string')

    # Invalid type raises ValidationError
    with pytest.raises(ValidationError) as exc_info:
        MetricDefinition(description="Test", extract="grep test", type='invalid')  # type: ignore
    assert "type" in str(exc_info.value).lower()


def test_metric_definition_missing_required_fields():
    """Metric definition requires description and extract fields."""
    # Missing description
    with pytest.raises(ValidationError) as exc_info:
        MetricDefinition(extract="grep test")  # type: ignore
    assert "description" in str(exc_info.value).lower()

    # Missing extract
    with pytest.raises(ValidationError) as exc_info:
        MetricDefinition(description="Test")  # type: ignore
    assert "extract" in str(exc_info.value).lower()


# ========== BackendConfig Tests ==========

def test_backend_option_command_template_validation():
    """Command template must contain $CMD and $ARGS placeholders."""
    # Valid templates
    BackendOptionConfig(command_template="$CMD $ARGS")
    BackendOptionConfig(command_template="perf stat -- $CMD $ARGS")
    BackendOptionConfig(command_template="mpirun -np 4 $CMD $ARGS")

    # Missing $CMD
    with pytest.raises(ValidationError) as exc_info:
        BackendOptionConfig(command_template="echo $ARGS")
    error_msg = str(exc_info.value)
    assert "$CMD" in error_msg
    assert "$ARGS" in error_msg

    # Missing $ARGS
    with pytest.raises(ValidationError) as exc_info:
        BackendOptionConfig(command_template="$CMD only")
    error_msg = str(exc_info.value)
    assert "$CMD" in error_msg
    assert "$ARGS" in error_msg

    # Missing both placeholders
    with pytest.raises(ValidationError) as exc_info:
        BackendOptionConfig(command_template="echo hello")
    error_msg = str(exc_info.value)
    assert "$CMD" in error_msg
    assert "$ARGS" in error_msg

    # Empty template is allowed (default)
    backend = BackendOptionConfig()
    assert backend.command_template == ""


def test_backend_option_defaults():
    """Backend option applies correct default values."""
    backend = BackendOptionConfig(command_template="$CMD $ARGS")
    assert backend.profiling is False, "Default profiling should be False"
    assert backend.composable is True, "Default composable should be True"
    assert backend.placeholders == {}, "Default placeholders should be empty dict"
    assert backend.version is None
    assert backend.description is None


def test_backend_config_requires_backend_options():
    """BackendConfig has default empty backend_options."""
    # Valid minimal config with explicit backend_options
    BackendConfig(backend_options={
        "local": BackendOptionConfig(command_template="$CMD $ARGS")
    })

    # BackendConfig() is valid with default empty backend_options
    config = BackendConfig()
    assert config.backend_options == {}


def test_backend_config_empty_backend_options():
    """BackendConfig can have empty backend_options dict."""
    # Empty dict is valid (though not useful in practice)
    config = BackendConfig(backend_options={})
    assert len(config.backend_options) == 0


def test_backend_config_metrics_validation():
    """Backend metrics must be valid MetricDefinition objects."""
    # Valid metrics
    config = BackendConfig(
        backend_options={"local": BackendOptionConfig(command_template="$CMD $ARGS")},
        metrics={
            "cycles": MetricDefinition(description="CPU cycles", extract="grep cycles")
        }
    )
    assert "cycles" in config.metrics

    # Invalid metric (missing required fields) raises ValidationError
    with pytest.raises(ValidationError):
        BackendConfig(
            backend_options={"local": BackendOptionConfig(command_template="$CMD $ARGS")},
            metrics={"invalid": {"description": "No extract field"}}  # type: ignore
        )


# ========== BenchmarkConfig Tests ==========

def test_benchmark_source_type_validation():
    """Source type must be 'git', 'path', or 'download'."""
    # Valid types
    BenchmarkSource(type='git', location='https://github.com/example/repo.git')
    BenchmarkSource(type='path', location='./benchmark.py')
    BenchmarkSource(type='download', location='https://example.com/bench.tar.gz')

    # Invalid type raises ValidationError
    with pytest.raises(ValidationError) as exc_info:
        BenchmarkSource(type='http', location='url')  # type: ignore
    assert "type" in str(exc_info.value).lower()


def test_benchmark_source_subdir_for_suites():
    """Subdir field enables suite benchmark support."""
    # Without subdir - typical standalone benchmark
    source = BenchmarkSource(type='path', location='./test.py')
    assert source.subdir is None

    # With subdir - suite benchmark like Rodinia
    source = BenchmarkSource(
        type='git',
        location='https://github.com/example/suite.git',
        subdir='opencl/pathfinder'
    )
    assert source.subdir == 'opencl/pathfinder'
    # Verify this enables building from subdirectory of cloned repo
    assert source.type == 'git'


def test_benchmark_entry_requires_essential_fields():
    """BenchmarkEntry requires entry_point, sources and build have defaults."""
    # sources and build now have defaults for suite-level inheritance
    # Only entry_point is strictly required
    entry = BenchmarkEntry(entry_point='./bench')
    assert entry.sources == []
    assert entry.build is not None

    # Missing entry_point still raises
    with pytest.raises(ValidationError) as exc_info:
        BenchmarkEntry(  # type: ignore
            sources=[BenchmarkSource(type='path', location='./test.py')],
            build=BenchmarkBuild()
        )
    assert "entry_point" in str(exc_info.value).lower()


def test_benchmark_build_mutually_exclusive_configs():
    """Benchmark can specify appimage OR docker build config."""
    # AppImage build
    build = BenchmarkBuild(
        appimage={'make_target': 'bench'},
        requirements=['numpy']
    )
    assert build.appimage is not None
    assert build.docker is None

    # Docker build
    build = BenchmarkBuild(
        docker={'base_image': 'gcc:11', 'build_commands': ['make']},
        system_deps=['libblas-dev']
    )
    assert build.appimage is None
    assert build.docker is not None

    # Both specified is allowed (though implementation will need to pick one)
    build = BenchmarkBuild(
        appimage={'make_target': 'bench'},
        docker={'base_image': 'gcc:11'}
    )
    assert build.appimage is not None
    assert build.docker is not None


def test_benchmark_config_requires_benchmarks_dict():
    """BenchmarkConfig requires benchmarks dictionary."""
    # Valid minimal config
    BenchmarkConfig(benchmarks={
        "test": BenchmarkEntry(
            sources=[BenchmarkSource(type='path', location='./test.py')],
            build=BenchmarkBuild(),
            entry_point='python3'
        )
    })

    # Missing benchmarks raises ValidationError
    with pytest.raises(ValidationError) as exc_info:
        BenchmarkConfig()  # type: ignore
    assert "benchmarks" in str(exc_info.value).lower()


# ========== ExperimentConfig Tests ==========

def test_experiment_config_allows_extra_fields():
    """Experiment config accepts arbitrary fields from includes."""
    # This is critical for include merging - fields from benchmark/backend
    # configs should be preserved in the merged experiment config
    config = ExperimentConfig(
        name='test_benchmark',
        entry_point='./bench',
        backend_name='local',
        custom_field={'nested': 'data'},
        another_field=[1, 2, 3]
    )
    # Verify extra fields are accessible
    assert config.name == 'test_benchmark'  # type: ignore
    assert config.entry_point == './bench'  # type: ignore
    assert config.backend_name == 'local'  # type: ignore
    assert config.custom_field == {'nested': 'data'}  # type: ignore
    assert config.another_field == [1, 2, 3]  # type: ignore


def test_experiment_config_include_merge_simulation():
    """Experiment config can represent merged include data."""
    # Simulate what happens after includes are merged:
    # benchmark.yaml contributes: name, entry_point, args
    # backend.yaml contributes: backend_options
    # experiment.yaml contributes: version, environment, options
    config = ExperimentConfig(
        version='1.0.0',
        environment={'OMP_NUM_THREADS': '4'},
        include=['bench.yaml', 'backend.yaml'],
        options={'experiment': 'test_exp'},
        # Fields from included files:
        name='matmul',
        entry_point='./matmul',
        args=['--size', '1024'],
        backend_options={'local': {'command_template': '$CMD $ARGS'}}
    )
    # Verify all fields are preserved
    assert config.version == '1.0.0'
    assert config.environment['OMP_NUM_THREADS'] == '4'
    assert config.name == 'matmul'  # type: ignore
    assert config.entry_point == './matmul'  # type: ignore


def test_experiment_config_options_structure():
    """Experiment options follow expected structure for runtime config."""
    config = ExperimentConfig(
        options={
            'experiment': 'test_exp',
            'description': 'Test description',
            'repeater_options': {
                'strategy': 'ci',
                'params': {'ci_width': 0.05, 'max_iterations': 100}
            },
            'verbosity': 'debug',
            'skip_sys_specs': True
        }
    )
    # Verify nested options structure
    assert config.options['experiment'] == 'test_exp'
    repeater_opts = config.options['repeater_options']
    assert repeater_opts['strategy'] == 'ci'
    assert repeater_opts['params']['ci_width'] == 0.05


# ========== WorkflowConfig Tests (currently minimal sequential workflow) ==========

def test_workflow_config_with_file_includes():
    """WorkflowConfig supports file includes."""
    from src.core.config.schema import WorkflowTask

    config = WorkflowConfig(
        version='1.0.0',
        workflow=[
            WorkflowTask(include='task1.yaml'),
            WorkflowTask(include='task2.yaml')
        ]
    )
    assert config.version == '1.0.0'
    assert config.description is None
    assert config.experiment is None
    assert len(config.workflow) == 2
    assert config.workflow[0].include == 'task1.yaml'
    assert config.workflow[0].task is None


def test_workflow_config_with_inline_tasks():
    """WorkflowConfig supports inline task definitions."""
    from src.core.config.schema import WorkflowTask

    config = WorkflowConfig(
        version='1.0.0',
        workflow=[
            WorkflowTask(
                task='sleep',
                backends=['local'],
                options={'repeater': 'COUNT', 'repeats': 5}
            ),
            WorkflowTask(
                task='matmul',
                backends=['local', 'perf'],
                options={'repeater': 'RSE'}
            )
        ]
    )
    assert len(config.workflow) == 2
    assert config.workflow[0].task == 'sleep'
    assert config.workflow[0].include is None
    assert config.workflow[1].backends == ['local', 'perf']


def test_workflow_config_with_description_and_experiment():
    """WorkflowConfig can include optional description and experiment name."""
    from src.core.config.schema import WorkflowTask

    config = WorkflowConfig(
        version='1.0.0',
        description='Test workflow',
        experiment='my_exp',
        workflow=[WorkflowTask(include='task1.yaml')]
    )
    assert config.description == 'Test workflow'
    assert config.experiment == 'my_exp'


def test_workflow_config_requires_version_and_workflow():
    """WorkflowConfig requires version and workflow fields."""
    from src.core.config.schema import WorkflowTask

    # Valid minimal config
    WorkflowConfig(
        version='1.0.0',
        workflow=[WorkflowTask(include='task1.yaml')]
    )

    # Missing version
    with pytest.raises(ValidationError) as exc_info:
        WorkflowConfig(workflow=[WorkflowTask(include='task1.yaml')])  # type: ignore
    assert "version" in str(exc_info.value).lower()

    # Missing workflow
    with pytest.raises(ValidationError) as exc_info:
        WorkflowConfig(version='1.0.0')  # type: ignore
    assert "workflow" in str(exc_info.value).lower()


def test_workflow_task_composition():
    """WorkflowTask supports include, inline, or hybrid composition."""
    from src.core.config.schema import WorkflowTask

    # Valid: include only
    task1 = WorkflowTask(include='task.yaml')
    assert task1.include == 'task.yaml'
    assert task1.task is None

    # Valid: inline task only
    task2 = WorkflowTask(task='sleep', backends=['local'])
    assert task2.task == 'sleep'
    assert task2.include is None

    # Valid: hybrid (include + inline overrides)
    task3 = WorkflowTask(include='base.yaml', task='sleep', options={'repeats': 100})
    assert task3.include == 'base.yaml'
    assert task3.task == 'sleep'
    assert task3.options == {'repeats': 100}

    # Valid: include + options override
    task4 = WorkflowTask(include='task.yaml', options={'repeats': 1000})
    assert task4.include == 'task.yaml'
    assert task4.options == {'repeats': 1000}

    # Invalid: neither specified
    with pytest.raises(ValidationError) as exc_info:
        WorkflowTask()
    assert "Must specify either" in str(exc_info.value)


# ========== WorkflowStep Tests (future DAG workflow support) ==========

def test_workflow_step_dependency_structure():
    """Workflow steps can express dependency relationships (future DAG support)."""
    # Step with no dependencies (can run immediately)
    step1 = WorkflowStep(id='step1', experiment='experiments/test1.yaml')
    assert step1.depends_on == []

    # Step depends on one previous step
    step2 = WorkflowStep(id='step2', experiment='experiments/test2.yaml', depends_on=['step1'])
    assert len(step2.depends_on) == 1

    # Step depends on multiple previous steps
    step3 = WorkflowStep(id='step3', experiment='experiments/test3.yaml', depends_on=['step1', 'step2'])
    assert len(step3.depends_on) == 2
