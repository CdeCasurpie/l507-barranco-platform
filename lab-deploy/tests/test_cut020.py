import importlib.util
import errno
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

path=Path(__file__).resolve().parents[1]/'tools/cut020_steps.py'
spec=importlib.util.spec_from_file_location('cut020',path)
cut=importlib.util.module_from_spec(spec);spec.loader.exec_module(cut)


class CutPairsTests(unittest.TestCase):
    def test_cross_mount_copy_is_verified_and_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.jpg';target=Path(tmp)/'target.jpg'
            source.write_bytes(b'original frame bytes')
            link=os.link
            def crossing(left,right):
                if Path(left)==source:
                    raise OSError(errno.EXDEV,'cross-device link')
                return link(left,right)
            with mock.patch.object(cut.os,'link',side_effect=crossing):
                self.assertEqual(cut.verified_link_or_copy(source,target),'verified-copy')
            self.assertEqual(source.read_bytes(),target.read_bytes())
            self.assertEqual(cut.verified_link_or_copy(source,target),'verified-existing')
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()),['source.jpg','target.jpg'])

    def test_existing_different_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';target=Path(tmp)/'target'
            source.write_bytes(b'original');target.write_bytes(b'user work')
            with self.assertRaisesRegex(AssertionError,'differs'):
                cut.verified_link_or_copy(source,target)
            self.assertEqual(target.read_bytes(),b'user work')

    def test_non_cross_mount_error_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';target=Path(tmp)/'target';source.write_bytes(b'original')
            with mock.patch.object(cut.os,'link',side_effect=PermissionError(errno.EACCES,'denied')):
                with self.assertRaises(PermissionError):cut.verified_link_or_copy(source,target)
            self.assertFalse(target.exists())

    def rows(self):
        rows=[]
        for i in range(970):
            t=i/2
            if 268<=t<280:continue
            rows.append({'seconds':t,'name':f'phone/frame_{round(t*1e6):012d}_b.jpg','kind':'baseline_2fps'})
        for i in range(120):
            t=268+i/10
            rows.append({'seconds':t,'name':f'phone/frame_{round(t*1e6):012d}_c.jpg','kind':'cut_10fps'})
        return sorted(rows,key=lambda row:row['seconds'])

    def test_temporal_density_and_order(self):
        rows=self.rows()
        self.assertEqual(len(rows),1066)
        self.assertEqual(sum(r['kind']=='cut_10fps' for r in rows),120)
        self.assertEqual(len({r['name'] for r in rows}),1066)
        self.assertTrue(all(a['seconds']<b['seconds'] for a,b in zip(rows,rows[1:])))

    def test_019_cut_keeps_continuity_with_context(self):
        rows=[]
        for i in range(1104):
            t=i/2
            if 408<=t<420:continue
            rows.append({'seconds':t,'name':f'phone/frame_{round(t*1e6):012d}_b.jpg','kind':'baseline_2fps'})
        for i in range(120):
            t=408+i/10
            rows.append({'seconds':t,'name':f'phone/frame_{round(t*1e6):012d}_c.jpg','kind':'cut_10fps'})
        self.assertEqual(len(rows),1200)
        pairs=set(cut.temporal_pairs(rows))
        by_time={round(r['seconds'],1):r['name'] for r in rows}
        for a,b in [(407.5,413.5),(414.0,420.5)]:
            self.assertIn(tuple(sorted((by_time[a],by_time[b]))),pairs)
        self.assertLessEqual(len(pairs),80000)

    def test_dense_interval_keeps_ten_second_matching_support(self):
        rows=self.rows();pairs=set(cut.temporal_pairs(rows))
        self.assertLessEqual(len(pairs),80000)
        by_time={round(r['seconds'],1):r['name'] for r in rows}
        self.assertIn(tuple(sorted((by_time[267.5],by_time[274.0]))),pairs)
        self.assertIn(tuple(sorted((by_time[274.0],by_time[281.5]))),pairs)
        self.assertNotIn(tuple(sorted((by_time[260.0],by_time[274.0]))),pairs)
        self.assertTrue(all(a!=b for a,b in pairs))
        self.assertIn(tuple(sorted((rows[0]['name'],rows[-1]['name']))),pairs)


if __name__=='__main__':unittest.main()
