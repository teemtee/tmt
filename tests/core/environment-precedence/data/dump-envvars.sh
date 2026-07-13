#!/bin/bash

LINE_PREFIX="${LINE_PREFIX:-}"

for line in $(env -0 | sort -z | tr '\0' '\n'); do echo "${LINE_PREFIX}: ${line}"; done
