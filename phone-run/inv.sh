echo PKG=$(dpkg-query -W -f="\${Package}:\${Status}
" 2>/dev/null | grep "install ok installed" | cut -d: -f1 | grep -iE "^(anydesk|teamviewer.*|rustdesk|tailscale|zerotier-one|x11vnc|tigervnc.*|xrdp|realvnc.*|nomachine|chrome-remote-desktop|cloudflared|ngrok|parsec|dwservice|meshagent|remmina-plugin-vnc)$" | tr "
" " ") SNAP=$(snap list 2>/dev/null | awk "NR>1{print \$1}" | grep -iE "anydesk|teamviewer|rustdesk|tailscale|zerotier|ngrok|cloudflared|remote" | tr "
" " ") FLAT=$(flatpak list --app --columns=application 2>/dev/null | grep -iE "anydesk|teamviewer|rustdesk|remote|parsec" | tr "
" " ") SVC=$(systemctl list-unit-files --no-legend 2>/dev/null | awk "{print \$1}" | grep -iE "anydesk|teamviewer|rustdesk|tailscale|zerotier|xrdp|vnc|cloudflared|ngrok|meshagent|dwagent" | tr "
" " ") ZT=$(ls /var/lib/zerotier-one/networks.d/ 2>/dev/null | grep -v local | tr "
" " ")
