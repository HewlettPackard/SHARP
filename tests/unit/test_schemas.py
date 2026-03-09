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
    """BenchmarkEntry requires sources, build, and entry_point."""
    # Missing sources
    with pytest.raises(ValidationError) as exc_info:
        BenchmarkEntry(  # type: ignore
            build=BenchmarkBuild(),
            entry_point='./bench'
        )
    assert "sources" in str(exc_info.value).lower()

    # Missing build
    with pytest.raises(ValidationError) as exc_info:
        BenchmarkEntry(  # type: ignore
            sources=[BenchmarkSource(type='path', location='./test.py')],
            entry_point='./bench'
        )
    assert "build" in str(exc_info.value).lower()

    # Missing entry_point
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


# ========== WorkflowConfig Tests ==========

def test_workflow_step_dependency_structure():
    """Workflow steps can express dependency relationships."""
    # Step with no dependencies (can run immediately)
    step1 = WorkflowStep(id='step1', benchmark='test1', backend='local')
    assert step1.depends_on == []

    # Step depends on one previous step
    step2 = WorkflowStep(id='step2', benchmark='test2', backend='local', depends_on=['step1'])
    assert len(step2.depends_on) == 1

    # Step depends on multiple previous steps
    step3 = WorkflowStep(id='step3', benchmark='test3', backend='local', depends_on=['step1', 'step2'])
    assert len(step3.depends_on) == 2


def test_workflow_config_requires_version_and_steps():
    """WorkflowConfig requires version and steps fields."""
    # Valid minimal config
    WorkflowConfig(
        version='1.0.0',
        steps=[WorkflowStep(id='s1', benchmark='b1', backend='local')]
    )

    # Missing version
    with pytest.raises(ValidationError) as exc_info:
        WorkflowConfig(steps=[WorkflowStep(id='s1', benchmark='b1', backend='local')])  # type: ignore
    assert "version" in str(exc_info.value).lower()

    # Missing steps
    with pytest.raises(ValidationError) as exc_info:
        WorkflowConfig(version='1.0.0')  # type: ignore
    assert "steps" in str(exc_info.value).lower()


def test_workflow_parallel_groups_structure():
    """Parallel groups enable concurrent step execution."""
    config = WorkflowConfig(
        version='1.0.0',
        steps=[
            WorkflowStep(id='step1', benchmark='test1', backend='local'),
            WorkflowStep(id='step2', benchmark='test2', backend='local'),
            WorkflowStep(id='step3', benchmark='test3', backend='local'),
        ],
        parallel_groups=[
            ['step1', 'step2'],  # step1 and step2 can run concurrently
            ['step3']             # step3 runs after the parallel group
        ]
    )
    # Verify structure supports parallelism specification
    assert len(config.parallel_groups) == 2
    assert config.parallel_groups[0] == ['step1', 'step2']
