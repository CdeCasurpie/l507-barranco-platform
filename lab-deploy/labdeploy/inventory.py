import concurrent.futures
import ipaddress
import json
import re
from pathlib import Path
import socket
import subprocess
import sys
import time


def discover(site, store, ssh):
    tools=str(Path(site['lab_tools']).expanduser())
    if tools not in sys.path:sys.path.insert(0,tools)
    try:
        import lab_inventory
        network,_,local=lab_inventory.discover_subnet()
        if site.get('subnet') and site['subnet']!='auto':
            network=ipaddress.ip_network(site['subnet'])
        ips=lab_inventory.scan_port22(network)
    except ImportError:
        network=ipaddress.ip_network(site['subnet'])
        local=None
        def open_port(ip):
            try:
                with socket.create_connection((str(ip),22),timeout=.5):return str(ip)
            except OSError:return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
            ips=[ip for ip in pool.map(open_port,network.hosts()) if ip]
    own=set()
    try:
        interfaces=json.loads(subprocess.check_output(['ip','-j','-4','addr'],text=True))
        own={a['local'] for interface in interfaces for a in interface.get('addr_info',[])}
    except (OSError,ValueError):pass
    if local:own.add(local)
    results={}
    def inspect(ip):
        try:
            return ip,ssh.call(ip,'probe',{},timeout=75)
        except Exception as exc:
            return ip,{'error':str(exc)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for ip,facts in pool.map(inspect,[ip for ip in ips if ip not in own]):
            tags=facts.get('tags',[])
            if len(tags)!=1 or tags[0] not in site['nodes']:continue
            tag=tags[0]
            if site['nodes'][tag] not in facts.get('macs',[]):
                continue
            if tag in results:
                results[tag]={'error':'Duplicate observed tag; enrollment blocked','available':False}
            else:
                results[tag]={'ip':ip,'available':True,'observed':time.time(),'facts':facts}
    for tag in site['nodes']:
        results.setdefault(tag,{'available':False,'error':'Not observed with matching tag/MAC'})
    store.write('inventory.json',results)
    return results


def selected(site,args):
    if args.all:
        return sorted(site['nodes'])
    tags=[]
    for value in args.targets.split(','):
        value=value.strip().upper()
        if not value:continue
        match=re.fullmatch(r'(?:L507[_-]?)?(\d{1,3})',value)
        tags.append('L507_'+match.group(1).zfill(3) if match else value)
    if not tags:raise ValueError('Specify at least one node')
    for tag in tags:
        if tag not in site['nodes']:raise ValueError('Unregistered/master target: '+tag)
    return list(dict.fromkeys(tags))
