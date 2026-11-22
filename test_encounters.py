"""The preset catalogue changes only physical starting conditions."""
import unittest

from galaxy_app.encounters import PRESETS, PHYSICAL_KEYS, get_preset, apply_preset, match_config


class EncounterPresetTests(unittest.TestCase):
    def test_profiles_are_distinct_and_fit_the_existing_controls(self):
        self.assertEqual(len(PRESETS), 7)
        self.assertEqual(len({p['id'] for p in PRESETS}), len(PRESETS))
        self.assertEqual(len({tuple(p['config'][k] for k in PHYSICAL_KEYS) for p in PRESETS}),len(PRESETS))
        for preset in PRESETS:
            c=preset['config']
            self.assertTrue(preset['label'] and preset['name'] and preset['description'])
            self.assertEqual(set(c),set(PHYSICAL_KEYS))
            self.assertTrue(-3 <= c['impact'] <= 3)
            self.assertTrue(.45 <= c['speed'] <= 2)
            self.assertTrue(.6 <= c['massratio'] <= 1.5)
            self.assertTrue(0 <= c['inclination'] <= 75)
            self.assertIn(c['spin'],(-1,1))
            self.assertIsInstance(c['isolated'],bool)

    def test_apply_retains_sampling_backend_and_seed(self):
        original=dict(seed=781,count=2048,tracer_count=15000,backend='numpy',softening=.15,
                      impact=-1.,speed=1.2,massratio=1.1,inclination=5.,spin=-1,isolated=False)
        for preset in PRESETS:
            actual=apply_preset(original,preset['id'])
            self.assertEqual(match_config(actual),preset['id'])
            for key in ('seed','count','tracer_count','backend','softening'):
                self.assertEqual(actual[key],original[key])
        self.assertEqual(original['impact'],-1.)

    def test_match_ignores_unrelated_fields_but_recognizes_custom_changes(self):
        c={**get_preset('sidepass')['config'],'seed':5,'count':512,'tracer_count':3000}
        self.assertEqual(match_config(c),'sidepass')
        c['speed']+=1e-12
        self.assertEqual(match_config(c),'sidepass')
        c['speed']+=.01
        self.assertEqual(match_config(c),'custom')
        self.assertEqual(match_config({}),'custom')
        c['speed']=float('nan')
        self.assertEqual(match_config(c),'custom')

    def test_get_returns_a_copy_and_unknown_ids_are_rejected(self):
        p=get_preset('sidepass');p['config']['speed']=2.;p['label']='changed'
        self.assertEqual(get_preset('sidepass')['config']['speed'],.9)
        self.assertNotEqual(get_preset('sidepass')['label'],'changed')
        with self.assertRaises(KeyError):get_preset('not-a-profile')


if __name__=='__main__':unittest.main()
