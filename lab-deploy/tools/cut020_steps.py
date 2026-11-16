"""Run-isolated local cut probe, temporal frame merge and bounded SfM overlay."""
import hashlib
import errno
import json
from pathlib import Path
import runpy
import sqlite3
import subprocess
import sys
import os
import shutil
import tempfile


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4194304),b''):h.update(block)
    return h.hexdigest()


def verified_link_or_copy(source,target):
    """Reuse immutable input; EXDEV is expected across container bind mounts."""
    source,target=Path(source),Path(target)
    assert source.is_file() and not source.is_symlink()
    assert not target.is_symlink(),'Refusing a symlink destination'
    expected=sha(source)
    if target.exists():
        assert target.is_file() and sha(target)==expected,'Existing derived file differs'
        return 'verified-existing'
    try:
        os.link(source,target)
        method='hardlink'
    except OSError as error:
        if error.errno!=errno.EXDEV:
            raise
        # Stage a complete copy on the destination mount, then publish without
        # replacing any existing destination. Only our own temporary is removed.
        fd,name=tempfile.mkstemp(prefix='.'+target.name+'.',dir=target.parent)
        temporary=Path(name)
        try:
            with os.fdopen(fd,'wb') as output,source.open('rb') as input_file:
                shutil.copyfileobj(input_file,output,length=4*1024**2)
                output.flush()
                os.fsync(output.fileno())
            assert sha(temporary)==expected,'Cross-mount copy checksum mismatch'
            os.link(temporary,target)
        finally:
            temporary.unlink(missing_ok=True)
        method='verified-copy'
    assert sha(target)==expected,'Published frame/mask differs from source'
    return method


def context(root):
    policy=json.loads((root/'cut-policy.json').read_text())
    source=Path(policy['source_output'])
    spec=json.loads((root/'reconstruction.json').read_text())
    out=root/'outputs'/('cuadra-'+policy.get('block_id','020'))/spec['full_experiment']
    return policy,source,out


def probe(root):
    from PIL import Image, ImageChops, ImageDraw
    policy,source,out=context(root)
    folder=root/'timing-probe'
    folder.mkdir()
    video=root/policy['video_relative_path']
    first=int(policy['start_seconds']*2)
    last=int(policy['end_seconds']*2)-1
    # Filter from video origin: preserve exactly the original fps filter phase.
    command=['ffmpeg','-hide_banner','-nostdin','-loglevel','error','-i',str(video),
             '-vf',f"fps=2,select='between(n,{first},{last})'",
             '-vsync','0','-frames:v',str(last-first+1),'-qscale:v','2',
             '-threads','4',str(folder/'probe_%06d.jpg')]
    subprocess.run(command,check=True)
    checks=[]
    targets=policy.get('target_image_ids',[547,548,549,550])
    stem=policy.get('video_stem','manzana_20')
    assert len(targets)==4
    for image_id in targets:
        baseline=source/'frames/phone'/f'{stem}_{image_id:06d}.jpg'
        candidate=folder/f'probe_{image_id-first:06d}.jpg'
        exact=sha(baseline)==sha(candidate)
        if not exact:
            with Image.open(baseline) as left,Image.open(candidate) as right:
                exact=left.size==right.size and ImageChops.difference(left.convert('RGB'),right.convert('RGB')).getbbox() is None
        assert exact,f'Frame/time correspondence not verified for {image_id}'
        checks.append({'image_id':image_id,'name':str(baseline.relative_to(source/'frames')),
                       'fps_filter_output_seconds':(image_id-1)/2,'pixels_verified':True})
    sheet=Image.new('RGB',(768,480),'#171717')
    draw=ImageDraw.Draw(sheet)
    for i,image_id in enumerate(targets):
        p=source/'frames/phone'/f'{stem}_{image_id:06d}.jpg'
        with Image.open(p) as image:
            image.thumbnail((384,216))
            x=(i%2)*384;y=(i//2)*240
            sheet.paste(image,(x,y))
            draw.text((x+8,y+218),f'View {image_id} | fps output {(image_id-1)/2:.1f}s',fill='white')
    sheet.save(root/'cut-contact-sheet.png')
    (root/'timing-check.json').write_text(json.dumps({
        'time_basis':'FFmpeg fps filter output PTS from original video origin',
        'not_claiming_exact_input_frame_pts':True,'checks':checks},indent=2))


def merge(root):
    sys.path.insert(0,'/work')
    from pipeline.masks import colmap_mask_path,openmvs_mask_path
    policy,source,out=context(root)
    extra=root/'extra-outputs'/('cuadra-'+policy.get('block_id','020'))/'cut_clip_10fps'
    frame_dir=out/'frames/phone';mask_dir=out/'masks/phone'
    frame_dir.mkdir(parents=True,exist_ok=True);mask_dir.mkdir(parents=True,exist_ok=True)
    entries=[]
    start,end=policy['start_seconds'],policy['end_seconds']
    removed=[]
    stem=policy.get('video_stem','manzana_20')
    baseline_frames=sorted((source/'frames/phone').glob(stem+'_*.jpg'))
    assert len(baseline_frames)==policy.get('baseline_frame_count',970)
    for p in baseline_frames:
        index=int(p.stem.rsplit('_',1)[1]);seconds=(index-1)/2
        if start<=seconds<end:
            removed.append({'original_image_id':index,'name':p.name,'seconds':seconds})
            continue
        entries.append({'seconds':seconds,'source_frame':str(p),
                        'source_mask':str(source/'masks/phone'/colmap_mask_path(p)),
                        'kind':'baseline_2fps','original_image_id':index})
    extra_frames=sorted((extra/'frames/phone').glob(stem+'_*.jpg'))
    assert len(extra_frames)==int((end-start)*10),'Unexpected 10 fps clip length'
    for i,p in enumerate(extra_frames):
        entries.append({'seconds':start+i/10,'source_frame':str(p),
                        'source_mask':str(extra/'masks/phone'/colmap_mask_path(p)),
                        'kind':'cut_10fps','original_image_id':None})
    entries.sort(key=lambda row:row['seconds'])
    for row in entries:
        label=f"frame_{round(row['seconds']*1000000):012d}_{'b' if row['kind']=='baseline_2fps' else 'c'}.jpg"
        target=frame_dir/label
        image=Path(row['source_frame']);mask=Path(row['source_mask'])
        assert image.is_file() and mask.is_file() and not image.is_symlink() and not mask.is_symlink()
        frame_method=verified_link_or_copy(image,target)
        mask_method=verified_link_or_copy(mask,mask_dir/colmap_mask_path(target))
        verified_link_or_copy(mask_dir/colmap_mask_path(target),out/'masks'/openmvs_mask_path(target))
        row.update(name='phone/'+label,frame_sha256=sha(target),mask_sha256=sha(mask))
        row.update(frame_transfer=frame_method,mask_transfer=mask_method)
    assert len(removed)==int((end-start)*2)
    assert len(entries)==len(baseline_frames)-len(removed)+len(extra_frames)
    (root/'frame-sampling.json').write_text(json.dumps({
        'start_seconds':start,'end_seconds':end,'outside_fps':2,'inside_fps':10,
        'frames':entries,'baseline_samples_replaced_in_variant_only':removed,
        'source_unchanged':True},indent=2))
    (out/'metrics').mkdir(exist_ok=True)
    (out/'metrics/masks_info.json').write_text(json.dumps({
        'backends_per_source':{'phone':['segformer','sam3']},
        'frames':len(entries),'reused_baseline_masks':len(entries)-len(extra_frames),
        'new_masks':len(extra_frames),'source_mask_metrics':str(source/'metrics/masks_info.json'),
        'new_mask_metrics':str(extra/'metrics/masks_info.json')},indent=2))


def sample(values,budget=120):
    if len(values)<=budget:return values
    return [values[round(i*(len(values)-1)/(budget-1))] for i in range(budget)]


def temporal_pairs(rows,window=10):
    rows=sorted(rows,key=lambda row:row['seconds'])
    pairs=set()
    for i,a in enumerate(rows):
        for b in rows[i+1:]:
            if b['seconds']-a['seconds']>window+1e-7:break
            pairs.add(tuple(sorted((a['name'],b['name']))))
    baseline=[r['name'] for r in rows if r['kind']=='baseline_2fps']
    for a in sample(baseline[:240]):
        for b in sample(baseline[-240:]):
            if a!=b:pairs.add(tuple(sorted((a,b))))
    assert len(pairs)<=80000
    return sorted(pairs)


def sfm(root):
    sys.path.insert(0,'/work')
    import pipeline.sfm as pipeline_sfm
    original=pipeline_sfm.run_cmd
    done=False
    rows=json.loads((root/'frame-sampling.json').read_text())['frames']
    pairs=temporal_pairs(rows)
    def command(argv,log,*args,**kwargs):
        nonlocal done
        if str(argv[1])=='mapper' and not done:
            done=True
            database=Path(argv[argv.index('--database_path')+1])
            path=database.parent/'time-and-loop-candidates.txt'
            assert not path.exists()
            path.write_text(''.join(a+' '+b+'\n' for a,b in pairs))
            original(['colmap','matches_importer','--database_path',str(database),
                      '--match_list_path',str(path),'--match_type','pairs',
                      '--SiftMatching.use_gpu','1','--SiftMatching.num_threads','4'],log)
            (database.parent/'time-and-loop-policy.json').write_text(json.dumps({
                'candidate_pairs':len(pairs),'temporal_window_seconds':10,
                'start_end_policy':'same 120 samples per 240 original endpoint frames',
                'geometric_thresholds_relaxed':False},indent=2))
        return original(argv,log,*args,**kwargs)
    pipeline_sfm.run_cmd=command
    config=str(root/'config-full.json')
    policy=json.loads((root/'cut-policy.json').read_text())
    sys.argv=['pipeline','run','--scene','cuadra-'+policy.get('block_id','020'),'--config',config,'--stages','sfm']
    runpy.run_module('pipeline',run_name='__main__')


if __name__=='__main__':
    mode,root=sys.argv[1],Path(sys.argv[2])
    {'probe':probe,'merge':merge,'sfm':sfm}[mode](root)
