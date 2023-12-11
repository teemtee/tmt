#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

USER="tmt-tester"
USER_HOME="/home/$USER"

CONNECT_RUN="/tmp/CONNECT"

# Where to get sources from?
# Set to '1' to use local checkout, otherwise git clone happens
# Plan cannot copy it to the right location so user is expected
# to do so (tests/full/repo_copy/.git has to exist as well)
COPY_IN="${COPY_IN:-0}"

# Set to desired tag/branch/commit (instead of the default branch)
# Used only if COPY_IN not equal 1
BRANCH="${BRANCH:-}"

# Set to '1' to keep tmt.spec as is
PRE_RELEASE="${PRE_RELEASE:-0}"

# Set to `test <options>` for test filtering
TEST_CMD="${TEST_CMD:-}"

# Run whole test suite ('all') or just scope not covered by CI ('complement')
SCOPE="${SCOPE:-all}"

set -o pipefail


get_value(){
    $USER_HOME/tmt/tests/execute/reboot/get_value.py "$1" "$2"
}

rlJournalStart
    rlPhaseStartSetup
        if ! rlIsFedora; then
            rlRun "rlImport epel/epel"
            rlRun "dnf config-manager --set-enabled epel"

            for repo in powertools extras crb codeready-builder; do
                real_repo_name="$(dnf repolist --all | grep -Eio "[-a-zA-Z0-9_]*$repo[-a-zA-Z0-9_]*" | head -n1)"
                if [[ -n "$real_repo_name" ]]; then
                    rlRun "dnf config-manager --set-enabled $real_repo_name"
                fi
            done

            # Better to install SOME tmt than none (python3-html2text missing on rhel-9)
            SKIP_BROKEN="--skip-broken"
        fi
        rlRun "dnf update -y" 0 "Update all packages"

        rlFileBackup /etc/sudoers
        id $USER &>/dev/null && {
            rlRun "pkill -9 -u $USER" 0,1
            rlRun "loginctl terminate-user $USER" 0,1
            rlRun "userdel -r $USER" 0 "Removing existing user"
        }
        rlRun "useradd $USER"
        rlRun "usermod --append --groups libvirt $USER"
        rlRun "echo '$USER ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers" 0 "password-less sudo for test user"
        rlRun "chmod 400 /etc/sudoers"
        rlRun "loginctl enable-linger $USER" # start session so /run/ directory is initialized

        # Making sure USER can r/w to the /var/tmp/tmt
        test -d /var/tmp/tmt && rlRun "chown $USER:$USER /var/tmp/tmt"

        # Use repo copied to tests/full/repo_copy directory
        # use `make bundle` if you run this outside of `make test`
        if [[ $COPY_IN -eq 1 ]]; then
            rlRun "mkdir -p $USER_HOME/tmt"
            rlRun "tar xzf repo_copy.tgz -C $USER_HOME/tmt"
            rlRun "pushd $USER_HOME/tmt"
            rlRun "chown root:root -R ."
        else
            # Clone repo otherwise
            rlRun "git clone https://github.com/teemtee/tmt $USER_HOME/tmt"
            rlRun "pushd $USER_HOME/tmt"
            [ -n "$BRANCH" ] && rlRun "git checkout --force '$BRANCH'"
        fi

        # Make current commit visible in the log
        rlRun "git show -s | cat"

        # Do not "patch" version for pre-release...
        [[ $PRE_RELEASE -ne 1 ]] && rlRun "sed 's/^Version:.*/Version: 9.9.9/' -i tmt.spec"

        # Build tmt packages
        rlRun "make build-deps" 0 "Install build dependencies"
        rlRun "make rpm" || rlDie "Failed to build tmt rpms"

        # After this we can use tmt (install freshly built rpms)
        rlRun "find $USER_HOME/tmt/tmp/RPMS -type f -name '*rpm' | xargs dnf install -y $SKIP_BROKEN"

        # Make sure that libvirt is running
        rlServiceStart "libvirtd"
        rlRun "su -l -c 'virsh -c qemu:///session list' $USER" || rlDie "qemu:///session not working, no point to continue"

        # Tests need VM machine for 'connect'
        # remove possible leftovers
        test -d $CONNECT_RUN && rlRun "rm -rf $CONNECT_RUN"
        test -d /var/tmp/tmt/testcloud && rlRun "rm -rf /var/tmp/tmt/testcloud"

        # Prepare fedora container image (https://tmt.readthedocs.io/en/latest/questions.html#container-package-cache)
        # but make it work with podman run  registry.fedoraproject.org/fedora:latest
        rlRun "su -l -c 'podman run -itd --name fresh fedora' $USER"
        rlRun "su -l -c 'podman exec fresh dnf makecache' $USER"
        # Install beakerlib as well, it is used a lot of times
        rlRun "su -l -c 'podman exec fresh dnf install -y beakerlib' $USER"
        rlRun "su -l -c 'podman commit fresh fresh' $USER"
        rlRun "su -l -c 'podman container rm -f fresh' $USER"
        rlRun "su -l -c 'podman tag fresh registry.fedoraproject.org/fedora:latest' $USER"
        rlRun "su -l -c 'podman images' $USER"

        # Prepare fedora VM
        rlRun "su -l -c 'tmt run --rm plans --default provision -h virtual finish' $USER" 0 "Fetch image"
        # Update metadata and install beakerlib into each image (should be a single one)
        for qcow in /var/tmp/tmt/testcloud/images/*qcow2; do
            rlRun "virt-customize -a $qcow --run-command 'dnf --refresh install -y beakerlib'" 0 "Update metadata and install beakerlib"
        done

        # Some plans install tmt into provisioned guests however host might not be the same version
        # check and compile rpms for guests if necessary
        rlRun -s "su -l -c 'podman run --rm fedora cat /etc/os-release | grep CPE_NAME=' $USER"
        image_cpe_name="$(cat $rlRun_LOG)"

        if [[ "$image_cpe_name" != "$(grep CPE_NAME= /etc/os-release)" ]]; then
            rlLog "Host OS differs from default image OS, compile new rpms"
            CONTAINER=BUILDER_$$
            rlRun "podman run --rm -v $USER_HOME/tmt:/tmp/tmt:Z -itd --name $CONTAINER fedora"
            rlRun "podman exec $CONTAINER dnf install -y 'dnf-command(builddep)' make"
            rlRun "podman exec -w /tmp/tmt $CONTAINER make build-deps"
            rlRun "podman exec -w /tmp/tmt $CONTAINER make rpm"
            rlRun "podman kill $CONTAINER"
        else
            rlLog "Host OS is the same as default image OS, no need to compile rpms"
        fi


        rlRun "su -l -c 'tmt run --id $CONNECT_RUN plans --default provision -h virtual' $USER"
        CONNECT_TO=$CONNECT_RUN/default/plan/provision/guests.yaml
        rlAssertExists $CONNECT_TO

        # Create new plans/provision/connect.fmf
        CONNECT_FMF=plans/provision/connect.fmf

        cat <<EOF > $CONNECT_FMF
summary: Connect to a running guest
provision:
    how: connect
    guest: $(get_value guest $CONNECT_TO)
    key: $(get_value key $CONNECT_TO)
    port: $(get_value port $CONNECT_TO)
    user: $(get_value user $CONNECT_TO)
EOF

        rlLog "$(cat $CONNECT_FMF)"

        # Delete the plan -> container vs host are not synced so rpms might not be installable
        rlRun 'rm -f plans/install/minimal.fmf'

        # Disable tests which need root #FIXME find a better way (one run with root...)
        for t in \
            /tests/run/permissions \
            /tests/prepare/install \
        ; do
            sed '/enabled:/d' -i $USER_HOME/tmt${t}/main.fmf
            echo 'enabled: false' >> $USER_HOME/tmt${t}/main.fmf
        done

        if [[ $SCOPE =~ 'complement' ]]; then
            rlLog "Patch $USER_HOME/tmt/plans/features/main.fmf"
            cat <<EOF >> $USER_HOME/tmt/plans/features/main.fmf
  - discover+:
      filter+: ' & tag:additional_coverage'
    tag+: [additional_coverage]
EOF
       fi

        # Make all local changes visible in the log
        rlRun "git diff | cat"
        if [ -z "$PLANS" ]; then
            if [[ $SCOPE =~ 'complement' ]]; then
                FILTER="--filter tag:additional_coverage"
            fi
            rlRun "su -l -c 'cd $USER_HOME/tmt; NO_COLOR=1 tmt -c how=full plans ls --enabled $FILTER > $USER_HOME/enabled_plans' $USER"
            PLANS="$(echo $(cat $USER_HOME/enabled_plans))"
        fi

        rlRun "chown -R $USER:$USER $USER_HOME" 0 "Make sure all files are readable by $USER"
    rlPhaseEnd

    for plan in $PLANS; do
        rlPhaseStartTest "Test: $plan"
            RUN="run$(echo $plan | tr '/' '-')"
            # Core of the test runs as $USER, -l should clear all BEAKER_envs.
            rlRun "su -l -c 'cd $USER_HOME/tmt; TMT_TEST_PIDFILE_ROOT=/tmp tmt -c how=full run --id $USER_HOME/$RUN -vvv -a report -h html plans --name $plan $TEST_CMD' $USER"

            # Upload file so one can review ASAP
            rlRun "tar czf /tmp/$RUN.tgz  --exclude *.qcow2 $USER_HOME/$RUN"
            rlFileSubmit /tmp/$RUN.tgz && rm -f /tmp/$RUN.tgz

            # Report individual test results to the beaker journal to make it visible
            # Run report display first
            rlRun -s "su -l -c 'cd $USER_HOME/tmt; tmt -c how=full run --id $USER_HOME/$RUN report -h display -v plans --name $plan $TEST_CMD' $USER"
            rlLog "Results of tests ran in this plan:"
            # Parse the output
            sed -n 's/^ *\(errr\|fail\|info\|pass\|warn\)/\1/p' "$rlRun_LOG" | while read -r RESULT TEXT; do
                case $RESULT in
                    errr)
                        rlLogError "$TEXT"
                        ;;
                    fail)
                        rlFail "$TEXT"
                        ;;
                    info)
                        rlLog "$TEXT"
                        ;;
                    pass)
                        rlPass "$TEXT"
                        ;;
                    warn)
                        rlLogWarning "$TEXT"
                        ;;
                esac
            done
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "su -l -c 'tmt run --id $CONNECT_RUN plans --default finish' $USER"
        rlFileRestore
        rlRun "pkill -u $USER" 0,1
        rlRun "loginctl terminate-user $USER" 0,1
        # Maybe add some delay?
        rlRun "userdel -fr $USER" "0-255"
    rlPhaseEnd
rlJournalEnd
