#!/bin/bash
set -x

if [ "$TMT_REBOOT_COUNT" == "0" ]; then
  echo 'Execute reboot during prepare step'
  tmt-reboot 0
fi
