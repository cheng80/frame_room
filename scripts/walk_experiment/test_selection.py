"""Guard the experimental selection gate; no models or network involved."""
import json
from pathlib import Path
import tempfile
import unittest
from build_review import PHASES, review_inputs, selection

def candidate(phase):
    return {'id':phase,'baseline_phase':phase,'baseline_confidence':0.95,
            'identity_verdict':'pass','leg_identity_observable':True,'motion_defects':[]}

class SelectionTests(unittest.TestCase):
    def test_high_confidence_cannot_override_failed_identity(self):
        frames=[candidate(p) for p in PHASES]
        frames[0]['identity_verdict']='fail'
        self.assertEqual(selection(frames)['proposed_order'],[])
    def test_high_confidence_cannot_resolve_unknown_leg(self):
        frames=[candidate(p) for p in PHASES]
        frames[2]['leg_identity_observable']=False
        self.assertIn(PHASES[2],selection(frames)['missing_phases'])
    def test_incomplete_cycle_stays_empty(self):
        self.assertEqual(selection([candidate(PHASES[0])])['proposed_order'],[])
    def test_full_order_still_requires_temporal_qa(self):
        result=selection(list(reversed([candidate(p) for p in PHASES])))
        self.assertEqual(result['proposed_order'],PHASES)
        self.assertFalse(result['production_approved'])
    def test_low_confidence_rejected(self):
        frames=[candidate(p) for p in PHASES];frames[1]['baseline_confidence']=0.7
        self.assertEqual(selection(frames)['proposed_order'],[])

class ReviewInputTests(unittest.TestCase):
    def test_editor_render_uses_only_corrected_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);(out/'editor-aligned').mkdir()
            old=[candidate(PHASES[0])];corrected=[candidate(PHASES[1])]
            (out/'observations.json').write_text(json.dumps({'frames':old}))
            (out/'observations-aligned.json').write_text(json.dumps({'frames':corrected}))
            self.assertEqual(review_inputs(out),(corrected,'observations-aligned.json'))

    def test_missing_corrected_observations_does_not_reuse_old_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);(out/'editor-aligned').mkdir()
            (out/'observations.json').write_text(json.dumps({'frames':[candidate(PHASES[0])]}))
            self.assertEqual(review_inputs(out),([],'observations-aligned.json'))
if __name__=='__main__':unittest.main()
