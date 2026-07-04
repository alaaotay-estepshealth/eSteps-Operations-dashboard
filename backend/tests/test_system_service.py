"""Tests for cross-system aggregate math."""
import pytest
from app.services.system_service import compute_weighted_success_rate


class _Sys:
    """Test double matching the fields the helper reads."""
    def __init__(self, success_rate_pct: float, total_executions: int):
        self.success_rate_pct = success_rate_pct
        self.total_executions = total_executions


def test_all_zero_executions_returns_none():
    systems = [_Sys(0.0, 0), _Sys(0.0, 0)]
    assert compute_weighted_success_rate(systems) is None


def test_single_healthy_system():
    systems = [_Sys(100.0, 50)]
    assert compute_weighted_success_rate(systems) == 100.0


def test_weighted_mean_mixed_systems():
    # 100% * 900 exec + 0% * 100 exec  => 90000 / 1000 = 90.0
    systems = [_Sys(100.0, 900), _Sys(0.0, 100)]
    assert compute_weighted_success_rate(systems) == 90.0


def test_zero_execution_systems_excluded_from_denominator():
    # Solar Leads with 0 executions must not drag the rate down.
    systems = [_Sys(100.0, 665), _Sys(0.0, 0)]
    assert compute_weighted_success_rate(systems) == 100.0


def test_partial_failure_rounds_to_one_decimal():
    # 74% * 100 exec + 100% * 200 exec => (7400 + 20000) / 300 = 91.333...
    systems = [_Sys(74.0, 100), _Sys(100.0, 200)]
    assert compute_weighted_success_rate(systems) == 91.3
