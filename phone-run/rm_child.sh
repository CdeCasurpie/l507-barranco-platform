# rm_child.sh PKG : purga el paquete de acceso remoto y sus restos (usuario utec_alumno, sudo)
P=$1; S(){ echo 'Utec@2026' | sudo -S -p '' "$@"; }
export DEBIAN_FRONTEND=noninteractive
S systemctl disable --now $P.service 2>&1 | tail -1
pkill -x $P 2>/dev/null; S pkill -x $P 2>/dev/null
S env DEBIAN_FRONTEND=noninteractive apt-get purge -y -q $P 2>&1 | grep -E "Purgando|Purging|Desinstalando|Removing|E:" | head -4
rm -rf ~/.anydesk ~/.config/rustdesk ~/.local/share/rustdesk 2>/dev/null; S rm -rf /etc/anydesk /root/.config/rustdesk /etc/apt/sources.list.d/anydesk*.list /etc/apt/sources.list.d/rustdesk*
if [ "$2" = cloudflared ]; then
  for u in cloudflared-update.timer cloudflared-update.service; do S systemctl disable --now $u 2>/dev/null; f=$(systemctl show -p FragmentPath --value $u); [ -n "$f" ] && S rm -f "$f"; done
  S rm -f /etc/apt/sources.list.d/tailscale.list; S systemctl daemon-reload
fi
echo "VERIF: pkg=$(dpkg-query -W -f='${Status}' $P 2>/dev/null || echo ausente) proc=$(pgrep -x $P | wc -l) units=$(systemctl list-unit-files --no-legend | grep -ciE "anydesk|rustdesk|cloudflared|tailscale")"
