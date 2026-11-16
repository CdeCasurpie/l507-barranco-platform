import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from report_campaign_timings import duration, lpt, native_attempts


class RetrospectiveTimingTests(unittest.TestCase):
    def test_mixed_duration_units_do_not_treat_milliseconds_as_minutes(self):
        self.assertAlmostEqual(duration('1h 2m 3s 4ms'), 3723.004)
        self.assertAlmostEqual(duration('477.540s'), 477.540)

    def test_failed_attempt_and_success_across_midnight_remain_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'dense.log'
            path.write_text(
                '23:59:40 [App     ] OpenMVS x64\n'
                '23:59:40 [App     ] Command line: DensifyPointCloud scene.mvs\n'
                '23:59:41 [App     ] aborted\n'
                '23:59:59 [App     ] OpenMVS x64\n'
                '23:59:59 [App     ] Command line: DensifyPointCloud scene.mvs\n'
                '00:00:02 [App     ] Densifying point-cloud completed: 100 points (2s500ms)\n'
            )
            end = datetime(2026, 11, 9, 0, 0, 2, tzinfo=timezone.utc).timestamp()
            os.utime(path, (end, end))
            failed, success = native_attempts(path)
            self.assertFalse(failed['successful'])
            self.assertIsNone(failed['compute_fusion_internal_s'])
            self.assertEqual(success['process_log_span_s'], 3)
            self.assertEqual(success['compute_fusion_internal_s'], 2.5)
            self.assertEqual(success['end_epoch_approx'], end)

    def test_more_machines_than_indivisible_jobs_cannot_reduce_longest_job(self):
        self.assertEqual(lpt([10, 6, 4], 1), 20)
        self.assertEqual(lpt([10, 6, 4], 2), 10)
        self.assertEqual(lpt([10, 6, 4], 19), 10)
