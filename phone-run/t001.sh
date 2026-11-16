#!/bin/bash
# t001.sh USER PASS IP... : desde la 001 intenta SSH por contraseña a cada IP (sin dejar known_hosts). BIND=ip para forzar origen.
U=$1; P=$2; shift 2
AP=$(mktemp); chmod 700 $AP; printf '#!/bin/sh\necho "%s"\n' "$P" > $AP
for ip in "$@"; do
  r=$(SSH_ASKPASS=$AP SSH_ASKPASS_REQUIRE=force timeout 20 ssh -n ${BIND:+-b $BIND} -o PubkeyAuthentication=no -o PreferredAuthentications=password \
      -o NumberOfPasswordPrompts=1 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o GlobalKnownHostsFile=/dev/null \
      -o ConnectTimeout=5 -o LogLevel=ERROR $U@$ip 'echo ENTRO' 2>&1)
  case "$r" in *ENTRO*) echo "$ip OK";; *"Permission denied"*) echo "$ip DENEGADO";; *"timed out"*|*"No route"*) echo "$ip SIN-RUTA";; *) echo "$ip ERROR: $(echo $r | cut -c1-80)";; esac
done
rm -f $AP
