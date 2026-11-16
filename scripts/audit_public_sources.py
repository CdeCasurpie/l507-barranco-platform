"""Static publication gate. Never imports operational scripts or prints secrets."""
import ast
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PATTERNS={
    'private_key':r'-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----',
    'service_token':r'\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{35,}|hf_[A-Za-z0-9]{25,}|sk-[A-Za-z0-9_-]{30,})\b',
    'bearer_literal':r'(?i)\bBearer\s+[A-Za-z0-9_=.-]{25,}',
    'credential_literal':r'''(?i)(?:password|passwd|LAB_SSH_PASSWORD|LAB_SUDO_PASSWORD|access_token|auth_token|api_key|secret)["']?\s*[:=]\s*["']([^"'\n]+)["']''',
}
FORBIDDEN_PARTS={'.state','state','exports','runtime','datasets','outputs','scratch','.venv'}
FORBIDDEN_SUFFIX={'.db','.bin','.ply','.mvs','.blend','.mp4','.jpg','.jpeg','.png','.pem','.key','.log'}


def main():
    process=subprocess.run(['git','ls-files','-z'],cwd=ROOT,capture_output=True)
    if process.returncode:
        raise SystemExit('Run from an initialized repository after staging sources.')
    names=[n for n in process.stdout.decode().split('\0') if n]
    if not names:raise SystemExit('No tracked/staged sources to audit.')
    findings=[]
    for name in names:
        p=ROOT/name
        if p.is_symlink():
            findings.append(dict(path=name,reason='symlink'));continue
        if any(part in FORBIDDEN_PARTS for part in p.relative_to(ROOT).parts):
            findings.append(dict(path=name,reason='runtime_or_state'))
        if p.suffix.lower() in FORBIDDEN_SUFFIX or p.stat().st_size>5*1024**2:
            findings.append(dict(path=name,reason='binary_or_large_file'))
        if p.name in {'.lab_credentials.json','site.json','known_hosts','hosts.yml'}:
            findings.append(dict(path=name,reason='private_configuration'))
        text=p.read_text()
        for category,pattern in PATTERNS.items():
            for match in re.finditer(pattern,text):
                findings.append(dict(path=name,line=text.count('\n',0,match.start())+1,reason=category))
        if p.suffix=='.py':
            try:ast.parse(text)
            except SyntaxError as error:
                findings.append(dict(path=name,line=error.lineno,reason='python_syntax'))
    print(json.dumps(dict(files=len(names),findings=findings,
                         note='Static checks are a gate, not proof that every possible secret format is recognized.'),indent=2))
    return bool(findings)


if __name__=='__main__':sys.exit(main())
