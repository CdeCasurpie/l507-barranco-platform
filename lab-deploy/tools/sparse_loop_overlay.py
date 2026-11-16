"""Run certified SfM with bounded start/end candidate matching before mapping.

Only this run's module reference is wrapped; the certified checkout is read-only.
Candidates are NOT assumed to be correspondences: COLMAP verifies them normally.
"""
import json
from pathlib import Path
import runpy
import sqlite3
import sys


def sample(values, budget=120):
    if len(values) <= budget:
        return values
    return [values[round(i*(len(values)-1)/(budget-1))] for i in range(budget)]


def closure_pairs(names):
    names = sorted(names)
    count = min(240, len(names)//3)  # At 2 fps, at most two minutes at each end.
    if not count:
        return []
    first, last = sample(names[:count]), sample(names[-count:])
    pairs = sorted({tuple(sorted((a,b))) for a in first for b in last if a != b})
    assert len(pairs) <= 14400
    assert all(not any(c.isspace() for c in name) for pair in pairs for name in pair)
    return pairs


def main():
    sys.path.insert(0, '/work')
    import pipeline.sfm as sfm
    original = sfm.run_cmd
    added = False

    def run_with_closure(command, log, *args, **kwargs):
        nonlocal added
        if len(command)>1 and str(command[1])=='mapper' and not added:
            added = True
            database = Path(command[command.index('--database_path')+1])
            with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as db:
                names = [r[0] for r in db.execute('SELECT name FROM images ORDER BY name')]
                before = db.execute('SELECT COUNT(*) FROM two_view_geometries WHERE rows>0').fetchone()[0]
            pairs = closure_pairs(names)
            path = database.parent/'start-end-candidates.txt'
            assert not path.exists(), 'Do not repeat closure matching automatically'
            path.write_text(''.join(a+' '+b+'\n' for a,b in pairs))
            if pairs:
                original(['colmap','matches_importer','--database_path',str(database),
                          '--match_list_path',str(path),'--match_type','pairs',
                          '--SiftMatching.use_gpu','1','--SiftMatching.num_threads','4'],log)
            with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as db:
                after = db.execute('SELECT COUNT(*) FROM two_view_geometries WHERE rows>0').fetchone()[0]
            (database.parent/'start-end-matching.json').write_text(json.dumps({
                'candidate_pairs':len(pairs),'verified_pairs_before':before,
                'verified_pairs_after':after,'policy':'first/last <=240 frames, <=120 samples each',
                'geometric_thresholds_relaxed':False,'geometry_approved':False},indent=2))
        return original(command, log, *args, **kwargs)

    sfm.run_cmd = run_with_closure
    runpy.run_module('pipeline', run_name='__main__')


if __name__=='__main__':
    main()
