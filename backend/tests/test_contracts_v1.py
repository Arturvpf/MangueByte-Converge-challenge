import copy
import json
from pathlib import Path
import unittest

from pydantic import ValidationError
from backend.app.contracts.v1 import (
    ContractError, ForecastResult, InvestigationReport, OrchestrationState,
    SkillCapacitySnapshot, ToolRequest, ToolResponse,
)

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures' / 'contracts'


def validate(model, value):
    return model.model_validate_json(json.dumps(value))


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.examples = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(FIXTURES.glob('*.json'))]
        self.example = self.examples[0]

    def test_shared_examples(self):
        self.assertEqual(len(self.examples), 2)
        self.assertEqual(len({e['request']['team_id'] for e in self.examples}), 2)
        for e in self.examples:
            self.assertTrue(e['synthetic'])
            request = validate(ToolRequest, e['request'])
            capacity = validate(SkillCapacitySnapshot, e['capacity'])
            response = validate(ToolResponse[InvestigationReport], e['investigation_response'])
            forecast = validate(ForecastResult, e['forecast'])
            for item in (capacity, response, forecast):
                self.assertEqual((item.tenant_id, item.team_id), (request.tenant_id, request.team_id))
            self.assertEqual(capacity.data_snapshot_id, request.data_snapshot_id)
            self.assertEqual(response.data_version, request.data_snapshot_id)
            self.assertEqual(forecast.data_snapshot_id, request.data_snapshot_id)

    def test_unknown_is_not_zero_and_units_are_explicit(self):
        obj = copy.deepcopy(self.example['capacity'])
        obj['rows'][0]['eligible_hours'] = None
        self.assertIsNone(validate(SkillCapacitySnapshot, obj).rows[0].eligible_hours)
        del obj['rows'][0]['eligible_hours']
        with self.assertRaises(ValidationError): validate(SkillCapacitySnapshot, obj)
        obj = copy.deepcopy(self.example['capacity'])
        obj['hours_unit'] = 'hours_per_week'
        with self.assertRaises(ValidationError): validate(SkillCapacitySnapshot, obj)
        obj['hours_unit'] = 'hours_per_period'
        obj['rows'][0]['availability_fraction'] = 91.0
        with self.assertRaises(ValidationError): validate(SkillCapacitySnapshot, obj)
        obj['rows'][0]['availability_fraction'] = 0.91
        obj['rows'][0]['cost_min'] = 5.0
        with self.assertRaises(ValidationError): validate(SkillCapacitySnapshot, obj)

    def test_scope_and_evidence_integrity(self):
        obj = copy.deepcopy(self.example['investigation_response'])
        obj['result']['team_id'] = 'other-team'
        with self.assertRaises(ValidationError): validate(ToolResponse[InvestigationReport], obj)
        obj = copy.deepcopy(self.example['investigation_response'])
        obj['evidence_refs'][0]['tenant_id'] = 'other-tenant'
        with self.assertRaises(ValidationError): validate(ToolResponse[InvestigationReport], obj)
        obj = copy.deepcopy(self.example['investigation_response']['result'])
        obj['hypotheses'][0].update(verification='supported', evidence_ids=['missing'], confidence=0.5)
        with self.assertRaises(ValidationError): validate(InvestigationReport, obj)
        obj['hypotheses'][0]['evidence_ids'] = []
        with self.assertRaises(ValidationError): validate(InvestigationReport, obj)

    def test_time_and_forecast(self):
        obj = copy.deepcopy(self.example['request'])
        obj['requested_at'] = '2026-11-07T12:00:00'
        with self.assertRaises(ValidationError): validate(ToolRequest, obj)
        obj = copy.deepcopy(self.example['forecast'])
        obj['horizon']['timezone'] = 'Not/AZone'
        with self.assertRaises(ValidationError): validate(ForecastResult, obj)
        obj = copy.deepcopy(self.example['forecast'])
        obj['history_end_exclusive'] = '2026-11-10'
        with self.assertRaises(ValidationError): validate(ForecastResult, obj)
        obj = copy.deepcopy(self.examples[1]['forecast'])
        obj['status'] = 'calibrated'
        with self.assertRaises(ValidationError): validate(ForecastResult, obj)
        obj = copy.deepcopy(self.examples[1]['forecast'])
        obj['points'][0]['lower'], obj['points'][0]['upper'] = 200.0, 500.0
        with self.assertRaises(ValidationError): validate(ForecastResult, obj)

    def test_errors_and_envelopes(self):
        error = {'code':'INSUFFICIENT_DATA', 'message':'Histórico insuficiente', 'retryable':False, 'details':[]}
        self.assertEqual(validate(ContractError, error).code.value, 'INSUFFICIENT_DATA')
        error['code'] = 'OTHER'
        with self.assertRaises(ValidationError): validate(ContractError, error)
        obj = copy.deepcopy(self.example['investigation_response'])
        obj['status'] = 'error'
        with self.assertRaises(ValidationError): validate(ToolResponse[InvestigationReport], obj)
        obj['result'], obj['error'] = None, {'code':'INSUFFICIENT_DATA', 'message':'Sem dados', 'retryable':False, 'details':[]}
        validate(ToolResponse[InvestigationReport], obj)
        obj['surprise'] = 1
        with self.assertRaises(ValidationError): validate(ToolResponse[InvestigationReport], obj)

    def test_state_cycle_bound(self):
        state = {**{k:self.example['request'][k] for k in ('schema_version','tenant_id','team_id','run_id','data_snapshot_id')}, 'state':'WAITING_INPUT','cycle_count':2,'cycle_limit':2,'trace_id':'trace-1'}
        validate(OrchestrationState, state)
        state['cycle_count'] = 3
        with self.assertRaises(ValidationError): validate(OrchestrationState, state)


if __name__ == '__main__':
    unittest.main()
