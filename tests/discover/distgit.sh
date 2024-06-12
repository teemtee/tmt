#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1


SERVER_PORT="9000"
MOCK_SOURCES_FILENAME='mock_sources'
TEST_DIR="$(pwd)"
PROVISION_HOW="${PROVISION_HOW:-local}"

# Make it easier to see what went wrong
export TMT_SHOW_TRACEBACK=1

# Assert tests name present in tests.yml detected in WORKDIR
function assert_tests(){
    test_yaml="$(find $1 -name tests.yaml -print)"
    rlAssertExists "$test_yaml" || return
    rlRun -s "yq '.[].name' < $test_yaml"
    shift
    while [ "$#" -gt 0 ]; do
        rlAssertGrep "$1" $rlRun_LOG
        shift
    done
}

# Assert tests name not present in tests.yml detected in WORKDIR
function assert_not_tests(){
    test_yaml="$(find $1 -name tests.yaml -print)"
    rlAssertExists "$test_yaml" || return
    rlRun -s "yq '.[].name' < $test_yaml"
    shift
    while [ "$#" -gt 0 ]; do
        rlAssertNotGrep "$1" $rlRun_LOG
        shift
    done
}

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun 'set -o pipefail'
        rlRun "git clone https://src.fedoraproject.org/rpms/tmt.git $tmp/tmt"
        export CLONED_RPMS_TMT=$tmp/tmt
        rlRun "cp data/plans.fmf $CLONED_RPMS_TMT/plans"
        # Append existing TMT_PLUGINS content
        rlRun "export TMT_PLUGINS=$(pwd)/data${TMT_PLUGINS:+:$TMT_PLUGINS}"
        rlRun 'pushd $tmp'

        # Server runs in $tmp
        rlRun "python3 -m http.server $SERVER_PORT &> server.out &"
        SERVER_PID="$!"
        rlRun "rlWaitForSocket $SERVER_PORT -t 5 -d 1"
        export SERVER_DIR="$(pwd)"

        rlRun "cp $TEST_DIR/data/*.patch $SERVER_DIR/"

        # Prepare cwd for mock distgit tests
        rlRun "mkdir $tmp/mock_distgit"
        export MOCK_DISTGIT_DIR=$tmp/mock_distgit
        rlRun "pushd $MOCK_DISTGIT_DIR"
        rlRun "git init" # should be git
        rlRun "tmt init" # should have an fmf tree (so CI can execute tmt plans)

        # One test in the dist-git
        echo 'test: echo' > top_test.fmf

        # Prepare with-tmt-1 (src contains tmt test and fmf root)
        (
            rlRun "mkdir -p $tmp/with-tmt-1/tests"
            (
                rlRun "cd $tmp/with-tmt-1"
                rlRun "tmt init"
            )
            # Checks packages added by patch thus fails if patching didn't happen properly
            echo 'test: rpm -q tree pcre' > "$tmp/with-tmt-1/tests/from-source.fmf"
            echo 'recommend: from-source' >> "$tmp/with-tmt-1/tests/from-source.fmf"
            touch $tmp/with-tmt-1/from-source.txt
            touch $tmp/outsider
            rlRun "tar czvf $tmp/with-tmt-1.tgz --directory $tmp with-tmt-1 outsider"
            rlRun "rm -rf $tmp/with-tmt-1 outsider"
        )

        # Prepare no-tmt-2 (src without any tmt metadata or fmf root)
        (
            rlRun "mkdir -p $tmp/no-tmt-2"
            echo -e '#!/bin/sh\necho WORKS'> $tmp/no-tmt-2/all_in_one
            chmod a+x $tmp/no-tmt-2/all_in_one

            rlRun "tar czvf $tmp/no-tmt-2.tgz --directory $tmp no-tmt-2"
            rlRun "rm -rf $tmp/no-tmt-2"
        )

        # Prepare other files for 'sources'
        for f in file.tgz.asc file.key something.gem; do
            rlRun "touch $SERVER_DIR/$f"
        done

        rlRun "popd"
    rlPhaseEnd

### No need to run these several times, 'local' is enough
if [[ $PROVISION_HOW == "local" ]] ; then
    for value in unset true false; do
        rlPhaseStartTest "Extract sources to find tests (merge: $value) - how:fmf"
            rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
            rlRun 'pushd $tmp'

            rlRun "git init && tmt init" # should be git with fmf tree

            # own "sources" for testing
            echo "no-tmt-2.tgz" > $MOCK_SOURCES_FILENAME
            sed -e '/^BuildArch:/aSource0: no-tmt-2.tgz' $TEST_DIR/data/demo.spec > demo.spec
            sed -e 's/package-src/no-tmt-2/' -i demo.spec
            # create 'test' inside dist-git
            echo 'test: no-tmt-2/all_in_one' > unit.fmf


# This can't be supported (mixing tests defined in discover and execute)
#         cat <<EOF > plans.fmf
# discover:
#     how: fmf
#     dist-git-source: true
#     dist-git-type: TESTING
# provision:
#     how: local
# execute:
#     how: tmt
#     script: no-tmt-2/all_in_one
# EOF

        cat <<EOF > plans.fmf
discover:
    how: fmf
    dist-git-source: true
    dist-git-type: TESTING
    dist-git-merge: $value
provision:
    how: local
execute:
    how: tmt
EOF

            if [[ "$value" == "unset" ]]; then
                rlRun "sed '/dist-git-merge:/d' -i plans.fmf"
            fi

            WORKDIR=/var/tmp/tmt/XXX
            WORKDIR_TESTS=$WORKDIR/plans/discover/default-0/tests

            rlRun -s "tmt run -vv --id $WORKDIR --scratch --keep"

            rlAssertGrep "/unit" $rlRun_LOG -F
            # 0 tests as we know real number only during prepare
            rlAssertGrep "summary: 0 tests selected" $rlRun_LOG -F

            rlAssertExists $WORKDIR_TESTS/no-tmt-2/all_in_one

            rlRun "popd"
            rlRun "rm -rf $tmp"
        rlPhaseEnd
    done

    rlPhaseStartTest "More source files (fmf root in one of them)"
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun 'pushd $tmp'

        rlRun "git init" # should be git
        rlRun "tmt init" # should has fmf tree

        (
            echo with-tmt-1.tgz
            echo no-tmt-2.tgz
        ) > $MOCK_SOURCES_FILENAME

        sed -e '/^BuildArch:/aSource0: with-tmt-1.tgz' $TEST_DIR/data/demo.spec > demo.spec
        sed -e '/^Source0/aSource1: no-tmt-2.tgz' -i demo.spec
        sed -e '/autosetup/d' -i demo.spec
        sed -e '/prep/atar -xzvf %{SOURCE0}\ntar -xzvf %{SOURCE1}' -i demo.spec

        WORKDIR=/var/tmp/tmt/XXX
        WORKDIR_SOURCE=$WORKDIR/default/plan/discover/default-0/source
        WORKDIR_TESTS=$WORKDIR/default/plan/discover/default-0/tests

        rlRun -s "tmt run --keep --id $WORKDIR --scratch plans --default \
             discover -vvv -ddd --how fmf --dist-git-source \
             --dist-git-type TESTING tests --name /tests/from-source provision -h local prepare"

        # Source dir has everything available
        rlAssertExists $WORKDIR_SOURCE/with-tmt-1/tests/from-source.fmf
        rlAssertExists $WORKDIR_SOURCE/with-tmt-1.tgz
        rlAssertExists $WORKDIR_SOURCE/no-tmt-2/all_in_one
        rlAssertExists $WORKDIR_SOURCE/no-tmt-2.tgz
        rlAssertExists $WORKDIR_SOURCE/outsider

        # Test dir has only fmf_root from source (so one less level)
        rlAssertExists $WORKDIR_TESTS/tests/from-source.fmf
        rlAssertNotExists $WORKDIR_TESTS/with-tmt-1/tests/from-source.fmf
        rlAssertNotExists $WORKDIR_TESTS/with-tmt-1.tgz
        rlAssertNotExists $WORKDIR_TESTS/no-tmt-2/all_in_one
        rlAssertNotExists $WORKDIR_TESTS/no-tmt-2.tgz
        rlAssertNotExists $WORKDIR_TESTS/outsider

        # Correct test selected
        assert_tests $WORKDIR /from-source

        rlRun "popd"
        rlRun "rm -rf $tmp"
    rlPhaseEnd



    rlPhaseStartTest "all source files are downloaded" # TODO merge with another phase
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun 'pushd $tmp'

        rlRun "git init && tmt init" # should be git with fmf tree

        (
            echo with-tmt-1.tgz
            echo file.tgz.asc
            echo file.key
            echo something.gem
        ) > $MOCK_SOURCES_FILENAME

        sed -e '/^BuildArch:/aSource0: with-tmt-1.tgz' $TEST_DIR/data/demo.spec > demo.spec
        sed -e 's/package-src/with-tmt-1/' -i demo.spec

        rlRun -s 'tmt run --id /var/tmp/tmt/XXX --scratch plans --default \
             discover -vvv -ddd --how fmf --dist-git-source \
             --dist-git-type TESTING tests --name /from-source provision -h local prepare'

        rlRun "popd"
        rlRun "rm -rf $tmp"
    rlPhaseEnd

    rlPhaseStartTest "Detect within extracted sources (inner fmf root is used)"
        rlRun 'pushd $MOCK_DISTGIT_DIR'

        echo "with-tmt-1.tgz" > $MOCK_SOURCES_FILENAME
        sed -e '/^BuildArch:/aSource0: with-tmt-1.tgz' $TEST_DIR/data/demo.spec > demo.spec
        sed -e 's/package-src/with-tmt-1/' -i demo.spec

        WORKDIR=/var/tmp/tmt/XXX
        WORKDIR_SOURCE=$WORKDIR/default/plan/discover/default-0/source
        WORKDIR_TESTS=$WORKDIR/default/plan/discover/default-0/tests

        rlRun -s 'tmt run --id $WORKDIR --scratch plans --default \
             discover -vvv -ddd --how fmf --dist-git-source \
             --dist-git-type TESTING prepare provision -h local'

        # Source dir has everything available
        rlAssertExists $WORKDIR_SOURCE/outsider
        rlAssertExists $WORKDIR_SOURCE/with-tmt-1
        rlAssertExists $WORKDIR_SOURCE/with-tmt-1.tgz

        # Test dir has only fmf_root from source
        rlAssertExists $WORKDIR_TESTS/tests/from-source.fmf
        rlAssertNotExists $WORKDIR_TESTS/outsider
        rlAssertNotExists $WORKDIR_TESTS/with-tmt-1
        rlAssertNotExists $WORKDIR_TESTS/with-tmt-1.tgz

        assert_tests $WORKDIR /from-source
        assert_not_tests $WORKDIR /top_test

        rlRun 'popd'
    rlPhaseEnd

    rlPhaseStartTest "Detect within extracted sources and join with plan data (still respect fmf root)"
        rlRun 'pushd $MOCK_DISTGIT_DIR'

        echo "with-tmt-1.tgz" > $MOCK_SOURCES_FILENAME
        sed -e '/^BuildArch:/aSource0: with-tmt-1.tgz' $TEST_DIR/data/demo.spec > demo.spec
        sed -e 's/package-src/with-tmt-1/' -i demo.spec

        WORKDIR=/var/tmp/tmt/XXX
        WORKDIR_SOURCE=$WORKDIR/default/plan/discover/default-0/source
        WORKDIR_TESTS=$WORKDIR/default/plan/discover/default-0/tests

        rlRun -s 'tmt run --id $WORKDIR --scratch plans --default \
            discover -v --how fmf --dist-git-source \
            --dist-git-type TESTING --dist-git-merge provision -h local prepare'

        # Source dir has everything available
        rlAssertExists $WORKDIR_SOURCE/outsider
        rlAssertExists $WORKDIR_SOURCE/with-tmt-1
        rlAssertExists $WORKDIR_SOURCE/with-tmt-1.tgz

        # Only fmf_root from source was merged
        rlAssertExists $WORKDIR_TESTS/tests/from-source.fmf
        rlAssertNotExists $WORKDIR_TESTS/outsider
        rlAssertNotExists $WORKDIR_TESTS/with-tmt-1
        rlAssertNotExists $WORKDIR_TESTS/with-tmt-1.tgz

        assert_tests $WORKDIR /top_test /tests/from-source
        rlRun 'popd'
    rlPhaseEnd

    rlPhaseStartTest "Detect within extracted sources and join with plan data (override fmf root)"
        rlRun 'pushd $MOCK_DISTGIT_DIR'

        echo "with-tmt-1.tgz rename-with-tmt-1.tgz" > $MOCK_SOURCES_FILENAME
        sed -e '/^BuildArch:/aSource0: rename-with-tmt-1.tgz' $TEST_DIR/data/demo.spec > demo.spec
        sed -e 's/package-src/with-tmt-1/' -i demo.spec

        WORKDIR=/var/tmp/tmt/XXX
        WORKDIR_SOURCE=$WORKDIR/default/plan/discover/default-0/source
        WORKDIR_TESTS=$WORKDIR/default/plan/discover/default-0/tests

        rlRun -s 'tmt run --id $WORKDIR --scratch plans --default \
            discover -v --how fmf --dist-git-source \
            --dist-git-type TESTING --dist-git-merge --dist-git-extract /with-tmt*/tests prepare provision -h local'

        # Source dir has everything available
        rlAssertExists $WORKDIR_SOURCE/outsider
        rlAssertExists $WORKDIR_SOURCE/with-tmt-1
        rlAssertExists $WORKDIR_SOURCE/rename-with-tmt-1.tgz

        # copy path set to /tests within sources, so with-tmt-1 is not copied
        rlAssertExists $WORKDIR_TESTS/from-source.fmf
        rlAssertNotExists $WORKDIR_TESTS/outsider
        rlAssertNotExists $WORKDIR_TESTS/with-tmt-1
        rlAssertNotExists $WORKDIR_TESTS/rename-with-tmt-1.tgz

        assert_tests $WORKDIR '"/top_test' '"/from-source'
        rlRun 'popd'
    rlPhaseEnd

    rlPhaseStartTest "Detect within extracted sources and join with plan data (strip fmf root)"
        rlRun 'pushd $MOCK_DISTGIT_DIR'

        echo "with-tmt-1.tgz rename-with-tmt.tgz" > $MOCK_SOURCES_FILENAME
        sed -e '/^BuildArch:/aSource0: rename-with-tmt.tgz' $TEST_DIR/data/demo.spec > demo.spec
        sed -e 's/package-src/with-tmt-1/' -i demo.spec

        WORKDIR=/var/tmp/tmt/XXX
        WORKDIR_SOURCE=$WORKDIR/default/plan/discover/default-0/source
        WORKDIR_TESTS=$WORKDIR/default/plan/discover/default-0/tests

        rlRun -s 'tmt run --id $WORKDIR --scratch plans --default \
            discover -v --how fmf --dist-git-source \
            --dist-git-type TESTING --dist-git-merge --dist-git-remove-fmf-root provision -h local prepare'

        # Source dir has everything available
        rlAssertExists $WORKDIR_SOURCE/outsider
        rlAssertExists $WORKDIR_SOURCE/with-tmt-1
        rlAssertExists $WORKDIR_SOURCE/rename-with-tmt.tgz

        # fmf root stripped and dist-git-extract not set so everything is copied
        rlAssertExists $WORKDIR_TESTS/with-tmt-1/tests/from-source.fmf
        rlAssertExists $WORKDIR_TESTS/outsider
        rlAssertExists $WORKDIR_TESTS/with-tmt-1
        # But not the tarball/patches..
        rlAssertNotExists $WORKDIR_TESTS/rename-with-tmt.tgz

        assert_tests $WORKDIR '"/top_test' '"/with-tmt-1/tests/from-source'
        rlRun 'popd'
    rlPhaseEnd

    rlPhaseStartTest "Run directly from the DistGit (Fedora) [cli]"
        rlRun 'pushd tmt'
        WORKDIR=/var/tmp/tmt/XXX
        rlRun -s 'tmt run --id $WORKDIR --keep --scratch plans --default \
            discover -v --how fmf --dist-git-source \
            tests --name tests/prepare/install$ provision -h local prepare'
         assert_tests $WORKDIR "/tests/prepare/install"
        rlRun 'popd'
    rlPhaseEnd

    rlPhaseStartTest "Run directly from the DistGit (Fedora) [plan]"
        rlRun 'pushd tmt'
        WORKDIR=/var/tmp/tmt/XXX
        rlRun -s 'tmt run --keep --id $WORKDIR --scratch plans --name distgit discover provision -h local prepare'
        assert_tests $WORKDIR "/tests/prepare/install"
        rlRun 'popd'
    rlPhaseEnd

    rlPhaseStartTest "URL is path to a local distgit repo"
        WORKDIR=/var/tmp/tmt/XXX
        rlRun -s 'tmt run --keep --scratch --id $WORKDIR plans --default \
            discover --how fmf --dist-git-source --dist-git-type fedora --url $CLONED_RPMS_TMT \
            --dist-git-merge tests --name tests/prepare/install$ prepare provision -h local'
        assert_tests $WORKDIR tests/prepare/install
    rlPhaseEnd

    for prefix in "" "/"; do
        rlPhaseStartTest "${prefix}path pointing to the fmf root in the extracted sources"
            rlRun 'pushd tmt'
            WORKDIR=/var/tmp/tmt/XXX
            rlRun -s "tmt run --keep --scratch --id $WORKDIR plans --default discover -v --how fmf \
            --dist-git-source --dist-git-merge --ref e2d36db --dist-git-extract ${prefix}tmt-1.7.0/tests/execute/framework/data \
            tests --name ^/tests/beakerlib/with-framework\$ prepare provision -h local"
            assert_tests $WORKDIR /tests/beakerlib/with-framework

            rlRun 'popd'
        rlPhaseEnd
    done

    rlPhaseStartTest "Specify URL and REF of DistGit repo (Fedora)"
        WORKDIR=/var/tmp/tmt/XXX
        rlRun -s 'tmt run --keep --scratch --id $WORKDIR plans --default discover -v --how fmf \
        --dist-git-source --ref e2d36db --dist-git-merge  --dist-git-init \
        --url https://src.fedoraproject.org/rpms/tmt.git \
        tests --name tests/prepare/install$  prepare provision -h local'
        assert_tests $WORKDIR "/tmt-1.7.0/tests/prepare/install"
    rlPhaseEnd

    rlPhaseStartTest "fmf and git root don't match"
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun 'pushd $tmp'

        rlRun "git init" # should be git

        (
            echo with-tmt-1.tgz
            echo no-tmt-2.tgz
        ) > $MOCK_SOURCES_FILENAME
        sed -e '/^BuildArch:/aSource0: with-tmt-1.tgz' $TEST_DIR/data/demo.spec > demo.spec
        sed -e '/^Source0:/aSource1: no-tmt-2.tgz' -i demo.spec
        sed -e '/autosetup/d' -i demo.spec
        sed -e '/prep/atar -xzvf %{SOURCE0}\ntar -xzvf %{SOURCE1}' -i demo.spec

        rlRun "mkdir aaaaaaaaaaaaaaaaaaaaa"
        rlRun "pushd aaaaaaaaaaaaaaaaaaaaa"
        rlRun "tmt init"

        WORKDIR=/var/tmp/tmt/XXX
        WORKDIR_SOURCE=$WORKDIR/default/plan/discover/default-0/source
        WORKDIR_TESTS=$WORKDIR/default/plan/discover/default-0/tests

        rlRun -s "tmt run --keep --id $WORKDIR --scratch plans --default \
             discover -vvv -ddd --how fmf --dist-git-source \
             --dist-git-type TESTING tests --name /tests/from-source provision -h local prepare"
        assert_tests $WORKDIR '"/tests/from-source'

        # Source dir has everything available
        rlAssertExists $WORKDIR_SOURCE/with-tmt-1/tests/from-source.fmf
        rlAssertExists $WORKDIR_SOURCE/with-tmt-1.tgz
        rlAssertExists $WORKDIR_SOURCE/no-tmt-2/all_in_one
        rlAssertExists $WORKDIR_SOURCE/no-tmt-2.tgz
        rlAssertExists $WORKDIR_SOURCE/outsider

        # Test dir has only fmf_root from source (so one less level)
        rlAssertExists $WORKDIR_TESTS/tests/from-source.fmf
        rlAssertNotExists $WORKDIR_TESTS/with-tmt-1/tests/from-source.fmf
        rlAssertNotExists $WORKDIR_TESTS/with-tmt-1.tgz
        rlAssertNotExists $WORKDIR_TESTS/no-tmt-2/all_in_one
        rlAssertNotExists $WORKDIR_TESTS/no-tmt-2.tgz
        rlAssertNotExists $WORKDIR_TESTS/outsider

        rlRun "popd"
        rlRun "popd"
        rlRun "rm -rf $tmp"
    rlPhaseEnd

    ### discover -h shell ###

    for build_phase in 'no' 'has'; do
        rlPhaseStartTest "Shell always merges the plan's git ($build_phase %build phase in spec)"
            rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
            rlRun 'pushd $tmp'

            rlRun "git init"
            echo no-tmt-2.tgz > $MOCK_SOURCES_FILENAME
            sed -e '/^BuildArch:/aSource0: no-tmt-2.tgz' $TEST_DIR/data/demo.spec > demo.spec
            sed -e 's/package-src/no-tmt-2/' -i demo.spec

            if [ "$build_phase" == "no" ]; then
                sed -e '/%build/d' -i demo.spec
                rlAssertNotGrep '%build' demo.spec
            else
                rlAssertGrep '%build' demo.spec
            fi

            rlRun "tmt init"
            # TODO try again with cd \$TMT_SOURCE_DIR/no-tmt-*
            # Fails after the rename
            cat <<EOF > plans.fmf
discover:
    how: shell
    tests:
    -   name: /file-exists
        test: ls \$TMT_SOURCE_DIR/no-tmt-2/all_in_one
        environment:
            FOO: bar
    -   name: /env-is-kept
        test: declare -p FOO && test \$FOO == bar
        environment:
            FOO: bar
    -   name: /run-it
        test: cd \$TMT_SOURCE_DIR/no-tmt-2 && sh all_in_one
    dist-git-source: true
    dist-git-type: TESTING
provision:
    how: local
execute:
    how: tmt
EOF

            WORKDIR=/var/tmp/tmt/XXX
            WORKDIR_SOURCE=$WORKDIR/plans/discover/default-0/source

            rlRun -s "tmt run --keep --id $WORKDIR --scratch -vvv"

            # Source dir has everything available
            rlAssertExists $WORKDIR_SOURCE/no-tmt-2/all_in_one
            rlAssertExists $WORKDIR_SOURCE/no-tmt-2.tgz

            rlRun "popd"
            rlRun "rm -rf $tmp"
        rlPhaseEnd
    done
rlPhaseStartTest "shell with download-only"
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun 'pushd $tmp'

        rlRun "git init"
        echo no-tmt-2.tgz > $MOCK_SOURCES_FILENAME
        sed -e '/^BuildArch:/aSource0: no-tmt-2.tgz' $TEST_DIR/data/demo.spec > demo.spec
        sed -e 's/package-src/no-tmt-2/' -i demo.spec

        rlRun "tmt init"
        cat <<EOF > plans.fmf
discover:
    how: shell
    tests:
    -   name: /tarball is there
        test: ls \$TMT_SOURCE_DIR
    dist-git-source: true
    dist-git-type: TESTING
    dist-git-download-only: true
provision:
    how: local
execute:
    how: tmt
EOF

        WORKDIR=/var/tmp/tmt/XXX
        WORKDIR_SOURCE=$WORKDIR/plans/discover/default-0/source

        rlRun -s "tmt run --keep --id $WORKDIR --scratch -vvv"

        # Tarball was not extracted
        rlAssertNotExists $WORKDIR_SOURCE/no-tmt-2/all_in_one
        # But downloaded
        rlAssertExists $WORKDIR_SOURCE/no-tmt-2.tgz
        rlAssertExists $WORKDIR_SOURCE/$MOCK_SOURCES_FILENAME


        rlRun "popd"
        rlRun "rm -rf $tmp"
        rlRun "rm -rf $WORKDIR"
    rlPhaseEnd
fi # END of "just in local" test block

    # TODO - incorporate into existing tests ...
    rlPhaseStartTest "dist-git with applied patches (shell)"
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun 'mkdir -p $tmp/distgit && pushd $tmp/distgit'
        rlRun "git init && tmt init" # should be git with fmf tree

        echo no-tmt-2.tgz > $MOCK_SOURCES_FILENAME
        echo add-txt.patch >> $MOCK_SOURCES_FILENAME
        sed -e '/^BuildArch:/aSource0: no-tmt-2.tgz' $TEST_DIR/data/demo.spec > demo.spec
        sed -e '/^BuildArch:/aBuildRequires: tree' -i demo.spec
        sed -e '/Source0/aPatch0: add-txt.patch' -i demo.spec
        sed -e 's/package-src/no-tmt-2/' -i demo.spec

        cat <<EOF > plans.fmf
discover:
    how: shell
    dist-git-source: true
    dist-git-type: TESTING
    dist-git-install-builddeps: true
    tests:
    - name: file from src
      test: test -e \$TMT_SOURCE_DIR/no-tmt-2/all_in_one
    - name: file from applied patch
      test: test -e \$TMT_SOURCE_DIR/no-tmt-2/by-patch.txt
    - name: buildrequire was installed
      test: rpm -q tree
provision:
    how: $PROVISION_HOW
execute:
    how: tmt
EOF
    # Prepare is required to apply patches ... warning should be printed
    #        rlRun -s "tmt run --scratch --id $tmp/rundir discover"
    #        rlAssertGrep "Sources will not be extracted, prepare step is not enabled" $rlRun_LOG

        rlRun -s "tmt run --keep --scratch --id $tmp/rundir -vvv --skip report"
        rlAssertGrep "total: 3 tests passed" $rlRun_LOG
        # File created by applying the patch is pulled back to the host
        rlAssertExists "$tmp/rundir/plans/discover/default-0/source/no-tmt-2/by-patch.txt"
    rlPhaseEnd


    rlPhaseStartTest "dist-git with applied patches (fmf)"
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun 'mkdir -p $tmp/distgit && pushd $tmp/distgit'
        rlRun "git init && tmt init" # should be git with fmf tree

        echo with-tmt-1.tgz > $MOCK_SOURCES_FILENAME
        echo add-tmt-test.patch >> $MOCK_SOURCES_FILENAME
        sed -e '/^BuildArch:/aSource0: with-tmt-1.tgz' $TEST_DIR/data/demo.spec > demo.spec
        sed -e '/Source0/aPatch0: add-tmt-test.patch' -i demo.spec
        sed -e 's/package-src/with-tmt-1/' -i demo.spec

        cat <<EOF > plans.fmf
discover:
    how: fmf
    dist-git-source: true
    dist-git-type: TESTING
provision:
    how: $PROVISION_HOW
execute:
    how: tmt
EOF
        rlRun -s "tmt run -kv --id $tmp/rundir --skip report"
        rlAssertGrep 'summary: 0 tests selected' $rlRun_LOG

        # Assert both tests are discovered
        assert_tests "$tmp/rundir" "/by-patch" "/tests/from-source"

        # Their recommend found
        rlRun -s "yq '.[].recommend' < $test_yaml"
        rlAssertGrep 'from-source' "$rlRun_LOG"

        # Their require found
        rlRun -s "yq '.[].require' < $test_yaml"
        rlAssertGrep 'tree' "$rlRun_LOG"

    rlPhaseEnd

    rlPhaseStartCleanup
        echo $SERVER_PID
        kill -9 $SERVER_PID
        rlRun 'popd'
    rlPhaseEnd
rlJournalEnd
