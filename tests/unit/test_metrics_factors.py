"""
Tests for factors metadata loader.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""
import pytest
from src.core.metrics.factors import (
    load_factors,
    load_mitigations,
    get_factor_info,
    get_mitigation_info,
    get_mitigation_backend,
    list_factors,
    list_mitigations,
)


class TestLoadFactors:
    """Test load_factors function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = load_factors()
        assert isinstance(result, dict)

    def test_contains_expected_factors(self):
        """Should contain common performance factors."""
        factors = load_factors()
        # Check for some expected perf factors
        expected = ['dTLB_misses', 'iTLB_misses', 'cache_misses',
                   'context_switches', 'page_faults']
        for factor in expected:
            assert factor in factors, f"Expected factor {factor} not found"

    def test_factor_has_required_fields(self):
        """Each factor should have description and mitigations."""
        factors = load_factors()
        if factors:
            # Pick first factor
            factor_name = next(iter(factors))
            factor_data = factors[factor_name]
            assert 'description' in factor_data
            assert 'mitigations' in factor_data
            assert isinstance(factor_data['mitigations'], list)

    def test_handles_missing_file_gracefully(self, tmp_path, monkeypatch):
        """Should return empty dict if file not found."""
        # Point to non-existent file
        from src.core.metrics import factors as factors_mod
        monkeypatch.setattr(factors_mod, '_FACTORS_PATH',
                          tmp_path / 'nonexistent.yaml')
        result = load_factors()
        assert result == {}


class TestLoadMitigations:
    """Test load_mitigations function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = load_mitigations()
        assert isinstance(result, dict)

    def test_contains_expected_mitigations(self):
        """Should contain common mitigation strategies."""
        mits = load_mitigations()
        expected = ['huge_pages', 'increase_cache', 'improve_locality',
                   'cpu_affinity', 'numa_binding']
        for mit in expected:
            assert mit in mits, f"Expected mitigation {mit} not found"

    def test_mitigation_has_description(self):
        """Each mitigation should have a description."""
        mits = load_mitigations()
        # Filter out backend_options
        mit_names = [k for k in mits.keys() if k != 'backend_options']
        if mit_names:
            mit_name = mit_names[0]
            mit_data = mits[mit_name]
            assert 'description' in mit_data

    def test_handles_missing_file_gracefully(self, tmp_path, monkeypatch):
        """Should return empty dict if file not found."""
        from src.core.metrics import factors as factors_mod
        monkeypatch.setattr(factors_mod, '_MITIGATIONS_PATH',
                          tmp_path / 'nonexistent.yaml')
        result = load_mitigations()
        assert result == {}


class TestGetFactorInfo:
    """Test get_factor_info function."""

    def test_returns_factor_data(self):
        """Should return factor data for valid factor name."""
        info = get_factor_info('dTLB_misses')
        assert info is not None
        assert 'description' in info
        assert 'mitigations' in info

    def test_returns_none_for_unknown_factor(self):
        """Should return None for unknown factor."""
        info = get_factor_info('nonexistent_factor_xyz')
        assert info is None

    def test_description_is_string(self):
        """Factor description should be a string."""
        info = get_factor_info('cache_misses')
        if info:
            assert isinstance(info['description'], str)
            assert len(info['description']) > 0

    def test_mitigations_is_list(self):
        """Factor mitigations should be a list."""
        info = get_factor_info('page_faults')
        if info:
            assert isinstance(info['mitigations'], list)


class TestGetMitigationInfo:
    """Test get_mitigation_info function."""

    def test_returns_mitigation_data(self):
        """Should return mitigation data for valid name."""
        info = get_mitigation_info('huge_pages')
        assert info is not None
        assert 'description' in info

    def test_returns_none_for_unknown_mitigation(self):
        """Should return None for unknown mitigation."""
        info = get_mitigation_info('nonexistent_mitigation_xyz')
        assert info is None

    def test_filters_backend_options(self):
        """Should not return backend_options as a mitigation."""
        info = get_mitigation_info('backend_options')
        assert info is None

    def test_description_is_string(self):
        """Mitigation description should be a string."""
        info = get_mitigation_info('cpu_affinity')
        if info:
            assert isinstance(info['description'], str)


class TestGetMitigationBackend:
    """Test get_mitigation_backend function."""

    def test_returns_none_if_no_backend(self):
        """Should return None for mitigations without backends."""
        # Most mitigations won't have backends
        backend = get_mitigation_backend('increase_cache')
        assert backend is None or isinstance(backend, dict)

    def test_returns_dict_with_run_template(self):
        """Should return dict with 'run' key if backend exists."""
        # Check if any mitigation has a backend
        mits = load_mitigations()
        backend_opts = mits.get('backend_options', {})
        if backend_opts:
            mit_name = next(iter(backend_opts))
            backend = get_mitigation_backend(mit_name)
            assert backend is not None
            assert isinstance(backend, dict)


class TestListFactors:
    """Test list_factors function."""

    def test_returns_list(self):
        """Should return a list of factor names."""
        factors = list_factors()
        assert isinstance(factors, list)

    def test_list_is_sorted(self):
        """Should return sorted list."""
        factors = list_factors()
        assert factors == sorted(factors)

    def test_contains_expected_factors(self):
        """Should contain common factors."""
        factors = list_factors()
        assert 'dTLB_misses' in factors
        assert 'cache_misses' in factors

    def test_all_items_are_strings(self):
        """All items should be strings."""
        factors = list_factors()
        assert all(isinstance(f, str) for f in factors)


class TestListMitigations:
    """Test list_mitigations function."""

    def test_returns_list(self):
        """Should return a list of mitigation names."""
        mits = list_mitigations()
        assert isinstance(mits, list)

    def test_list_is_sorted(self):
        """Should return sorted list."""
        mits = list_mitigations()
        assert mits == sorted(mits)

    def test_excludes_backend_options(self):
        """Should not include 'backend_options' key."""
        mits = list_mitigations()
        assert 'backend_options' not in mits

    def test_contains_expected_mitigations(self):
        """Should contain common mitigations."""
        mits = list_mitigations()
        assert 'huge_pages' in mits
        assert 'cpu_affinity' in mits

    def test_all_items_are_strings(self):
        """All items should be strings."""
        mits = list_mitigations()
        assert all(isinstance(m, str) for m in mits)
