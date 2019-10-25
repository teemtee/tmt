#!/bin/bash
# run.sh /path/to/workdir TYPE
#
#   TYPE of exectution:
#       plain|beakerlib
#
#

set -e

DEBUG=y

main () {
  last=""

  type="$1"
  plan="$(basename -s '.yaml' "$2")"

  name=''
  test=''
  path=''
  duration=''
  environment=''

  IFS=''
  while read line; do
    key="$(cut -d':' -f1 <<< "$line" | trim)"
    val="$(cut -d':' -f2- <<< "$line" | trim)"

    debug "> $line"

    grep -q '^\s' <<< "$line" && {
      m=
      [[ "$key" == 'name' ]] && { m=y; name="$val"; }
      [[ "$key" == 'test' ]] && { m=y; test="$val"; }
      [[ "$key" == 'path' ]] && { m=y; path="$val"; }
      [[ "$key" == 'duration' ]] && { m=y; duration="$val"; }
      [[ "$key" == 'environment' ]] && { m=y; environment="$val"; }

      [[ -n "$m" ]] || error "unknown test variable: $line"
      :
    } || {
      [[ "$last" == '' ]] || \
        runtest "$type" "$plan" "$name" "$test" "$path" "$duration" "$environment"

      last="$type$plan$name"

      name="$key"
      test=''
      path=''
      duration=''
      environment=''
    }
  done

  [[ "$type$plan$name" == "$last" ]] || \
    runtest "$type" "$plan" "$name" "$test" "$path" "$duration" "$environment"
}

runtest () {
  type="$1"
  plan="$2"
  name="$3"
  test="$4"
  path="$5"
  duration="$6"
  environment="$7"

  debug "> > runtest" "$type" "$plan" "$name" "$test" "$path" "$duration" "$environment"

  [[ -z "$environment" ]] || environment="env -i $environment "
  [[ -z "$duration" ]] || duration="timeout '$duration' "

  #pushd .$plan/$path # ?

  cmd="${environment}${duration}${test}"
  debug "> > > $cmd"
  #bash -c "$c" > stdout.log 2> stderr.log

  #popd

}

# Helpers
abort () {
  echo "Failure: $@" >&2
  exit 1
}

error () {
  echo "Error: $@" >&2
}

beakerlib () {
  abort "NYI: beakerlib tests run"
}

trim () {
  sed -e 's/ *$//g' \
      -e 's/^ *//g'
}

debug () {
  [[ -z "$DEBUG" ]] || echo "> $@" >&2
}

### INIT checks
# TODO #

### RUN
[[ -n "$1" ]] || abort "path to workdir is missing"
cd "$1" || abort "Failed to cd '$1'"

[[ -z "$2" || "$2" == 'plain' ]] && TYPE=plain || {
  [[ "$2" == 'beakerlib' || "$2" == 'whatever' ]] && {
    TYPE="$2"
    exit 0
  }
  abort "Unknown tests execution type: $2"
}

find -type f -name '*.yaml' \
  | while read file; do
      debug main "$TYPE" "$file"
      main "$TYPE" "$file" < <( grep -v '^$' "$file" )
      echo
    done
