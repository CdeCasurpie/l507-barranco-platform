from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from park_memory_recovery import bounded_source


class MaskCacheTests(unittest.TestCase):
    def test_eviction_preserves_mapping_results(self):
        source = '''
def prepare(pairs):
    cache = {}
    results = []
    for key in pairs:
        camera, out_camera = key
        if key not in cache:
            cache[key] = sampling_map(camera, out_camera)
        results.append(cache[key])
    return results, len(cache)
'''
        plain = {'sampling_map':lambda camera,target:(camera*7,target*13)}
        fixed = dict(plain)
        exec(source,plain)
        exec(bounded_source(source),fixed)
        pairs = [(i,i+1) for i in range(100)]*2
        expected, old_cache = plain['prepare'](pairs)
        result, new_cache = fixed['prepare'](pairs)
        self.assertEqual(result,expected)
        self.assertEqual(old_cache,100)
        self.assertLessEqual(new_cache,2)

    def test_unknown_source_is_rejected(self):
        with self.assertRaises(AssertionError):
            bounded_source('def changed(): pass')
