"""Guard the experimental selection gate; no models or network involved."""
import unittest
from build_review import PHASES, selection

def candidate(phase):
    return {'id':phase,'baseline_phase':phase,'baseline_confidence':0.95,
            'phase':phase,'confidence':0.99,'usable_noul':0.99,
            'identity_verdict':'pass','leg_identity_observable':True,'motion_defects':[]}

class SelectionTests(unittest.TestCase):
    def test_jev_cannot_override_failed_identity(self):
        frames=[candidate(p) for p in PHASES]
        frames[0]['identity_verdict']='fail'
        self.assertEqual(selection(frames,'phase','confidence',True)['proposed_order'],[])
    def test_unknown_leg_is_not_known_from_jev(self):
        frames=[candidate(p) for p in PHASES]
        frames[2]['leg_identity_observable']=False
        self.assertIn(PHASES[2],selection(frames,'phase','confidence',True)['missing_phases'])
    def test_incomplete_cycle_stays_empty(self):
        self.assertEqual(selection([candidate(PHASES[0])])['proposed_order'],[])
    def test_full_order_still_requires_temporal_qa(self):
        result=selection(list(reversed([candidate(p) for p in PHASES])))
        self.assertEqual(result['proposed_order'],PHASES)
        self.assertFalse(result['production_approved'])
    def test_low_confidence_rejected(self):
        frames=[candidate(p) for p in PHASES];frames[1]['baseline_confidence']=0.7
        self.assertEqual(selection(frames)['proposed_order'],[])
if __name__=='__main__':unittest.main()
