# Nice trick for one VM and multiple runs

```
  # boot up the machine
  $ tmt run -d provision -h virtual

  # Add the machine entry to be used in all runs
  $ ./conn-helper.sh plans/main.fmf

  # run tmt as usual...
  $ tmt run -ad prepare -h shell -s "sudo dnf install -y 'dnf-command(copr)' && dnf copr enable -y packit/psss-tmt-156 && sudo dnf install -y tmt"

  # TODO: FIX - destroy the instance
  $ tmt run --id ...

  # Workaround:
  $ vagrant global-status | grep -E ' (running|preparing) ' | tail -n -1 | sed -e 's/\s*$//' | cut -d' ' -f1 | xargs -rn1 vagrant destroy -f

```
