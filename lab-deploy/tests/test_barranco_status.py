import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

path=Path(__file__).resolve().parents[1]/'tools/barranco_status.py'
spec=importlib.util.spec_from_file_location('barranco_status',path)
status=importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


class StatusTests(unittest.TestCase):
    def test_remote_query_compiles_and_has_no_mutating_command(self):
        code=status.REMOTE.replace('ASSIGNMENT',repr({'node_tag':'L507_022','mac':'test',
                                                      'work_root':'/data/photogrammetry/campaigns/test'}))
        compile(code,'remote-status','exec')
        for forbidden in ('write_text(', '.unlink(', 'Popen(', "'docker','run'", "'systemctl','start'"):
            self.assertNotIn(forbidden,code)

    def test_terrestrial_uses_original_download_and_separate_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            original={'block_id':'016-023','work_root':'/data/photogrammetry/campaigns/x/all'}
            variant=dict(original,work_root='/data/photogrammetry/campaigns/x/terrestrial')
            (root/'assignments.json').write_text(json.dumps({'assignments':[original]}))
            (root/'terrestrial-bindings.json').write_text(json.dumps({'assignments':[variant]}))
            rows=status.assignments(root,{},False)
            self.assertEqual(rows[0]['work_root'],variant['work_root'])
            self.assertEqual(rows[0]['download_root'],original['work_root'])
            self.assertEqual(json.loads((root/'assignments.json').read_text())['assignments'][0],original)

    def test_cold_gpu_does_not_hide_thermal_failure(self):
        row={'block':'019','node':'L507_004','group':'nueva','download':'downloaded',
             'state':'failed','stage':'masks','worker_alive':False,'gpu_live':{'c':35},
             'error':'SAFETY STOP: sustained gpu_c=81.00'}
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            status.display([row])
        self.assertIn('FALLO',output.getvalue())
        self.assertIn('35°C',output.getvalue())
        self.assertIn(row['error'],output.getvalue())
        self.assertEqual(status.duration(3661),'01:01:01')


if __name__=='__main__':
    unittest.main()
