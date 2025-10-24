"""
Unit tests for Pydantic configuration schemas.

Tests validate schema structure, field validation, and error handling
for ExperimentConfig, BackendConfig, BenchmarkConfig, and related models.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

import unittest
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


class TestMetricDefinition(unittest.TestCase):
    """Test MetricDefinition schema validation."""

    def test_metric_definition_defaults(self):
        """Test that metric definition applies correct defaults."""
        metric = MetricDefinition(
            description="Test metric",
            extract="grep test | awk '{print $1}'"
        )
        # Verify defaults are applied correctly
        self.assertTrue(metric.lower_is_better, "Default lower_is_better should be True")
        self.assertEqual(metric.type, 'numeric', "Default type should be 'numeric'")
        self.assertIsNone(metric.units, "Default units should be None")

    def test_metric_definition_type_validation(self):
        """Test metric type must be 'numeric' or 'string'."""
        # Valid types
        MetricDefinition(description="Test", extract="grep test", type='numeric')
        MetricDefinition(description="Test", extract="grep test", type='string')

        # Invalid type should raise ValidationError
        with self.assertRaises(ValidationError) as context:
            MetricDefinition(description="Test", extract="grep test", type='invalid')  # type: ignore
        self.assertIn("type", str(context.exception).lower())

    def test_metric_definition_missing_required_fields(self):
        """Test metric definition requires description and extract fields."""
        # Missing description
        with self.assertRaises(ValidationError) as context:
            MetricDefinition(extract="grep test")  # type: ignore
        self.assertIn("description", str(context.exception).lower())

        # Missing extract
        with self.assertRaises(ValidationError) as context:
            MetricDefinition(description="Test")  # type: ignore
        self.assertIn("extract", str(context.exception).lower())


class TestBackendConfig(unittest.TestCase):
    """Test BackendConfig and BackendOptionConfig schema validation."""

    def test_backend_option_command_template_validation(self):
        """Test command template must contain $CMD and $ARGS placeholders."""
        # Valid template
        BackendOptionConfig(command_template="$CMD $ARGS")
        BackendOptionConfig(command_template="perf stat -- $CMD $ARGS")
        BackendOptionConfig(command_template="mpirun -np 4 $CMD $ARGS")

        # Missing $CMD
        with self.assertRaises(ValidationError) as context:
            BackendOptionConfig(command_template="echo $ARGS")
        error_msg = str(context.exception)
        self.assertIn("$CMD", error_msg)
        self.assertIn("$ARGS", error_msg)

        # Missing $ARGS
        with self.assertRaises(ValidationError) as context:
            BackendOptionConfig(command_template="$CMD only")
        error_msg = str(context.exception)
        self.assertIn("$CMD", error_msg)
        self.assertIn("$ARGS", error_msg)

        # Missing both
        with self.assertRaises(ValidationError) as context:
            BackendOptionConfig(command_template="echo hello")
        error_msg = str(context.exception)
        self.assertIn("$CMD", error_msg)
        self.assertIn("$ARGS", error_msg)

        # Empty template is allowed (default)
        backend = BackendOptionConfig()
        self.assertEqual(backend.command_template, "")

    def test_backend_option_defaults(self):
        """Test backend option applies correct defaults."""
        backend = BackendOptionConfig(command_template="$CMD $ARGS")
        self.assertFalse(backend.profiling, "Default profiling should be False")
        self.assertTrue(backend.composable, "Default composable should be True")
        self.assertEqual(backend.placeholders, {}, "Default placeholders should be empty dict")
        self.assertIsNone(backend.version)
        self.assertIsNone(backend.description)

    def test_backend_config_requires_backend_options(self):
        """Test BackendConfig requires at least backend_options field."""
        # Valid minimal config
        BackendConfig(backend_options={
            "local": BackendOptionConfig(command_template="$CMD $ARGS")
        })

        # Missing backend_options should fail
        with self.assertRaises(ValidationError) as context:
            BackendConfig()  # type: ignore
        self.assertIn("backend_options", str(context.exception).lower())

    def test_backend_config_empty_backend_options(self):
        """Test BackendConfig can have empty backend_options dict."""
        # Empty dict is valid (though not useful)
        config = BackendConfig(backend_options={})
        self.assertEqual(len(config.backend_options), 0)

    def test_backend_config_metrics_validation(self):
        """Test backend metrics must be valid MetricDefinition objects."""
        # Valid metrics
        config = BackendConfig(
            backend_options={"local": BackendOptionConfig(command_template="$CMD $ARGS")},
            metrics={
                "cycles": MetricDefinition(description="CPU cycles", extract="grep cycles")
            }
        )
        self.assertIn("cycles", config.metrics)

        # Invalid metric (missing required fields) should fail
        with self.assertRaises(ValidationError):
            BackendConfig(
                backend_options={"local": BackendOptionConfig(command_template="$CMD $ARGS")},
                metrics={"invalid": {"description": "No extract field"}}  # type: ignore
            )


class TestBenchmarkConfig(unittest.TestCase):
    """Test BenchmarkConfig and related schema validation."""

    def test_benchmark_source_type_validation(self):
        """Test source type must be 'git', 'path', or 'download'."""
        # Valid types
        BenchmarkSource(type='git', location='https://github.com/example/repo.git')
        BenchmarkSource(type='path', location='./benchmark.py')
        BenchmarkSource(type='download', location='https://example.com/bench.tar.gz')

        # Invalid type should raise ValidationError
        with self.assertRaises(ValidationError) as context:
            BenchmarkSource(type='http', location='url')  # type: ignore
        self.assertIn("type", str(context.exception).lower())

    def test_benchmark_source_subdir_for_suites(self):
        """Test subdir field enables suite benchmark support."""
        # Without subdir - typical standalone benchmark
        source = BenchmarkSource(type='path', location='./test.py')
        self.assertIsNone(source.subdir)

        # With subdir - suite benchmark like Rodinia
        source = BenchmarkSource(
            type='git',
            location='https://github.com/example/suite.git',
            subdir='opencl/pathfinder'
        )
        self.assertEqual(source.subdir, 'opencl/pathfinder')
        # Verify this enables building from subdirectory of cloned repo
        self.assertEqual(source.type, 'git')

    def test_benchmark_entry_requires_essential_fields(self):
        """Test BenchmarkEntry requires sources, build, and entry_point."""
        # Missing sources
        with self.assertRaises(ValidationError) as context:
            BenchmarkEntry(  # type: ignore
                build=BenchmarkBuild(),
                entry_point='./bench'
            )
        self.assertIn("sources", str(context.exception).lower())

        # Missing build
        with self.assertRaises(ValidationError) as context:
            BenchmarkEntry(  # type: ignore
                sources=[BenchmarkSource(type='path', location='./test.py')],
                entry_point='./bench'
            )
        self.assertIn("build", str(context.exception).lower())

        # Missing entry_point
        with self.assertRaises(ValidationError) as context:
            BenchmarkEntry(  # type: ignore
                sources=[BenchmarkSource(type='path', location='./test.py')],
                build=BenchmarkBuild()
            )
        self.assertIn("entry_point", str(context.exception).lower())

    def test_benchmark_build_mutually_exclusive_configs(self):
        """Test benchmark can specify appimage OR docker build config."""
        # AppImage build
        build = BenchmarkBuild(
            appimage={'make_target': 'bench'},
            requirements=['numpy']
        )
        self.assertIsNotNone(build.appimage)
        self.assertIsNone(build.docker)

        # Docker build
        build = BenchmarkBuild(
            docker={'base_image': 'gcc:11', 'build_commands': ['make']},
            system_deps=['libblas-dev']
        )
        self.assertIsNone(build.appimage)
        self.assertIsNotNone(build.docker)

        # Both specified is allowed (though implementation will need to pick one)
        build = BenchmarkBuild(
            appimage={'make_target': 'bench'},
            docker={'base_image': 'gcc:11'}
        )
        self.assertIsNotNone(build.appimage)
        self.assertIsNotNone(build.docker)

    def test_benchmark_config_requires_benchmarks_dict(self):
        """Test BenchmarkConfig requires benchmarks dictionary."""
        # Valid minimal config
        BenchmarkConfig(benchmarks={
            "test": BenchmarkEntry(
                sources=[BenchmarkSource(type='path', location='./test.py')],
                build=BenchmarkBuild(),
                entry_point='python3'
            )
        })

        # Missing benchmarks should fail
        with self.assertRaises(ValidationError) as context:
            BenchmarkConfig()  # type: ignore
        self.assertIn("benchmarks", str(context.exception).lower())


class TestExperimentConfig(unittest.TestCase):
    """Test ExperimentConfig schema validation."""

    def test_experiment_config_allows_extra_fields(self):
        """Test experiment config accepts arbitrary fields from includes."""
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
        self.assertEqual(config.name, 'test_benchmark')  # type: ignore
        self.assertEqual(config.entry_point, './bench')  # type: ignore
        self.assertEqual(config.backend_name, 'local')  # type: ignore
        self.assertEqual(config.custom_field, {'nested': 'data'})  # type: ignore
        self.assertEqual(config.another_field, [1, 2, 3])  # type: ignore

    def test_experiment_config_include_merge_simulation(self):
        """Test experiment config can represent merged include data."""
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
        self.assertEqual(config.version, '1.0.0')
        self.assertEqual(config.environment['OMP_NUM_THREADS'], '4')
        self.assertEqual(config.name, 'matmul')  # type: ignore
        self.assertEqual(config.entry_point, './matmul')  # type: ignore

    def test_experiment_config_options_structure(self):
        """Test experiment options follow expected structure for runtime config."""
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
        self.assertEqual(config.options['experiment'], 'test_exp')
        repeater_opts = config.options['repeater_options']
        self.assertEqual(repeater_opts['strategy'], 'ci')
        self.assertEqual(repeater_opts['params']['ci_width'], 0.05)


class TestWorkflowConfig(unittest.TestCase):
    """Test WorkflowConfig schema validation."""

    def test_workflow_step_dependency_structure(self):
        """Test workflow steps can express dependency relationships."""
        # Step with no dependencies (can run immediately)
        step1 = WorkflowStep(id='step1', benchmark='test1', backend='local')
        self.assertEqual(step1.depends_on, [])

        # Step depends on one previous step
        step2 = WorkflowStep(id='step2', benchmark='test2', backend='local', depends_on=['step1'])
        self.assertEqual(len(step2.depends_on), 1)

        # Step depends on multiple previous steps
        step3 = WorkflowStep(id='step3', benchmark='test3', backend='local', depends_on=['step1', 'step2'])
        self.assertEqual(len(step3.depends_on), 2)

    def test_workflow_config_requires_version_and_steps(self):
        """Test WorkflowConfig requires version and steps fields."""
        # Valid minimal config
        WorkflowConfig(
            version='1.0.0',
            steps=[WorkflowStep(id='s1', benchmark='b1', backend='local')]
        )

        # Missing version
        with self.assertRaises(ValidationError) as context:
            WorkflowConfig(steps=[WorkflowStep(id='s1', benchmark='b1', backend='local')])  # type: ignore
        self.assertIn("version", str(context.exception).lower())

        # Missing steps
        with self.assertRaises(ValidationError) as context:
            WorkflowConfig(version='1.0.0')  # type: ignore
        self.assertIn("steps", str(context.exception).lower())

    def test_workflow_parallel_groups_structure(self):
        """Test parallel groups enable concurrent step execution."""
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
        self.assertEqual(len(config.parallel_groups), 2)
        self.assertEqual(config.parallel_groups[0], ['step1', 'step2'])


if __name__ == '__main__':
    unittest.main()
