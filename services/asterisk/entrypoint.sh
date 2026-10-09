#!/bin/sh
# Fail-closed startup: render config from env (render.py validates everything), start the admin
# sidecar, then run Asterisk in the foreground.
set -eu

python3 /opt/omnidome/render.py

# admin sidecar (reload / registration status only) runs as the asterisk user
su -s /bin/sh asterisk -c "python3 /opt/omnidome/admin.py" &

exec asterisk -f -U asterisk -G asterisk
