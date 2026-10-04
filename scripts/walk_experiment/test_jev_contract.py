"""Regression cases for rounded probabilities observed in the paid API response."""
import unittest
from jev_compare import PHASES, SafeError, validate_response


def payload(values, choice='unknown'):
    return {'model':'jev-1.13.0', 'usage':{'input_tokens':10,'output_tokens':10},
            'answers':{'phase_000':{'type':'choice','choice':choice,'confidence':0.9,
                                  'probabilities':dict(zip(PHASES,values))}}}


class RoundedProbabilityTests(unittest.TestCase):
    request={'questions':{'phase_000':{'type':'choice'}}}

    def test_rounded_total_099_is_retained_without_normalizing(self):
        result=validate_response(payload([0.01]*8+[0.91]),self.request)
        self.assertAlmostEqual(sum(result['answers']['phase_000']['probabilities'].values()),0.99)

    def test_rounded_total_101_is_retained(self):
        validate_response(payload([0.01]*8+[0.93]),self.request)

    def test_grossly_invalid_rounded_mass_is_rejected(self):
        with self.assertRaisesRegex(SafeError,'invalid_probability_sum'):
            validate_response(payload([0.09]*9),self.request)

    def test_extra_precision_does_not_get_rounding_exception(self):
        with self.assertRaisesRegex(SafeError,'invalid_probability_sum'):
            validate_response(payload([0.011]*8+[0.902]),self.request)

    def test_rounding_does_not_allow_non_maximum_choice(self):
        with self.assertRaisesRegex(SafeError,'choice_not_argmax'):
            validate_response(payload([0.01]*8+[0.91],choice='near_contact'),self.request)


if __name__=='__main__':unittest.main()
