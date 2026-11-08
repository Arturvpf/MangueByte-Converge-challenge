import copy
from decimal import Decimal as D
import json
from pathlib import Path
import unittest

from backend.app.contracts.v1 import DemandSnapshot, ErrorCode, SkillCapacitySnapshot
from backend.app.metrics.engine import Allocation, MetricsError, homogeneous_metrics, prepare_matrix, validate_allocations


def example():
    data = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/contracts/aurora.json').read_text(encoding='utf-8'))
    return data['capacity'], data['demand']


def matrix(c, d):
    return prepare_matrix(SkillCapacitySnapshot.model_validate_json(json.dumps(c)), DemandSnapshot.model_validate_json(json.dumps(d)))


class MetricsTests(unittest.TestCase):
    def metrics(self, **kwargs):
        values = dict(headcount=11, nominal_hours_per_person=42, availability=D('.91'), cases_per_hour=D('2.27'), demand_cases=1200)
        values.update(kwargs)
        return homogeneous_metrics(**values)

    def test_reference(self):
        r = self.metrics()
        self.assertEqual(r.effective_hours, D('420.42'))
        self.assertEqual(r.capacity_cases, D('954.3534'))
        self.assertEqual((r.required_headcount, r.headcount_gap), (14, 3))
        self.assertEqual(r.fte, D('10.01'))
        self.assertEqual(r.effective_availability, D('.91'))
        self.assertEqual(r.ipd, D(1200) / D('954.3534'))

    def test_overtime_effective_not_availability_adjusted_twice(self):
        r = self.metrics(overtime_effective_hours=42)
        self.assertEqual(r.capacity_cases, D('1049.6934'))
        self.assertEqual(r.overtime_fte, 1)
        self.assertEqual(r.required_headcount, 14)

    def test_zero_denominators_and_zero_demand(self):
        r = self.metrics(headcount=0, demand_cases=0)
        self.assertIsNone(r.ipd)
        self.assertIsNone(r.effective_availability)
        self.assertEqual(r.required_headcount, 0)
        r = self.metrics(nominal_hours_per_person=0)
        self.assertIsNone(r.fte)
        self.assertIsNone(r.required_headcount)
        self.assertIsNone(r.headcount_gap)
        self.assertIsNone(self.metrics(availability=0).required_headcount)

    def test_invalid_values_and_units(self):
        for name, value in [('headcount', None), ('headcount', 1.5), ('headcount', True), ('availability', D('NaN')), ('availability', 1.01), ('cases_per_hour', -1), ('demand_cases', float('inf'))]:
            with self.subTest(name=name, value=value), self.assertRaises(MetricsError):
                self.metrics(**{name: value})
        with self.assertRaises(MetricsError) as e:
            self.metrics(hours_unit='hours_per_week')
        self.assertEqual(e.exception.code, ErrorCode.UNIT_MISMATCH)

    def test_shared_pool_and_allocation_limits(self):
        c, d = example()
        m = matrix(c, d)
        self.assertEqual(m.pools[0].available_hours, 320)
        self.assertEqual([r.eligible_hours for r in m.rows], [320, 200])
        self.assertIsNone(m.demand[0][1])
        validate_allocations(m, [Allocation('pool-day', 'skill-support', 'shift-day', D(120)), Allocation('pool-day', 'skill-triage', 'shift-day', D(200))])
        with self.assertRaises(MetricsError):
            validate_allocations(m, [Allocation('pool-day', 'skill-support', 'shift-day', D(121)), Allocation('pool-day', 'skill-triage', 'shift-day', D(200))])
        with self.assertRaises(MetricsError):
            validate_allocations(m, [Allocation('pool-day', 'skill-triage', 'shift-day', D(201))])
        with self.assertRaises(MetricsError):
            validate_allocations(m, [Allocation('pool-day', 'unknown', 'shift-day', D(1))])

    def test_unknown_limit_blocks_even_zero_allocation(self):
        c, d = example()
        c['pools'][0]['available_hours'] = None
        m = matrix(c, d)
        with self.assertRaises(MetricsError):
            validate_allocations(m, [Allocation('pool-day', 'skill-support', 'shift-day', D(0))])

    def test_scope_and_period(self):
        c, d = example()
        d['team_id'] = 'another'
        with self.assertRaises(MetricsError) as e:
            matrix(c, d)
        self.assertEqual(e.exception.code, ErrorCode.FORBIDDEN_SCOPE)
        c, d = example()
        d['records'][0]['period']['end_exclusive'] = '2026-11-08'
        with self.assertRaises(MetricsError) as e:
            matrix(c, d)
        self.assertEqual(e.exception.code, ErrorCode.UNIT_MISMATCH)

    def test_multi_pool_row_and_duplicate_allocations(self):
        c, d = example()
        c['pools'].append({'pool_id': 'pool-two', 'available_hours': 80})
        c['rows'][0]['pool_ids'].append('pool-two')
        m = matrix(c, d)
        validate_allocations(m, [Allocation('pool-day', 'skill-support', 'shift-day', D(240)), Allocation('pool-two', 'skill-support', 'shift-day', D(80))])
        with self.assertRaises(MetricsError):
            validate_allocations(m, [Allocation('pool-day', 'skill-support', 'shift-day', D(241)), Allocation('pool-two', 'skill-support', 'shift-day', D(80))])
        with self.assertRaises(MetricsError):
            validate_allocations(m, [Allocation('pool-two', 'skill-support', 'shift-day', D(1))] * 2)


if __name__ == '__main__':
    unittest.main()
