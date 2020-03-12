#!/bin/bash
set -e

bash -n "$0"

[[ -n "$1" ]] && {
  OF="$(readlink -e "$1")"
  touch "$OF"
  shift
  :
} || {
  OF="/dev/null"
}

[[ -n "$1" ]] && {
  D="$1"
  shift
  :
} || {
  CON="$(vagrant global-status | grep -E ' (running|preparing) ' | tail -n -1 | sed -e 's/\s*$//')"
  [[ -n "$CON" ]] || exit 1
  echo "Using '$CON'"
  D="$(echo "$CON" | tr -s '\t' ' ' | rev | cut -d' ' -f1 | rev)"
}

[[ -n "$D" ]]
cd "$D"

set -o pipefail

IP="$(vagrant ssh-config | grep ' HostName ' | cut -d' ' -f4)"
KY="$(vagrant ssh-config | grep ' IdentityFile ' | cut -d' ' -f4)"
US="$(vagrant ssh-config | grep ' User ' | cut -d' ' -f4)"

set +e

# TODO: FIX
#[[ "$OF" == '/dev/null' ]] || {
#  set -x
#  sed -i 's/provision:\n\s*how: connect\n\s*guest: \S*\n\s*user:\S*\n\s*key: \S*//' "$OF"
#  { set +x ;} &> /dev/null
#}

cat <<EOL | tee -a /dev/stderr >> "$OF"

provision:
    how: connect
    guest: '$IP'
    user: '$US'
    key: '$KY'

EOL
