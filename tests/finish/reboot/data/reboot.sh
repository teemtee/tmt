#!/bin/bash

if [ "$TMT_REBOOT_COUNT" == "0" ]; then
  echo 'Execute reboot during finish step'
  tmt-reboot 0
fi
