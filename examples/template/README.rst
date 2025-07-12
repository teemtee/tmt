
==================================================================
                        tmt test template
==================================================================

When creating a new ``tmt`` test it is recommended to use the test
template provided in this directory. In order to be able to use it
directly from the ``tmt test create`` command you might want to
symlink it to your configuration::

    ln -sr test.sh ~/.config/tmt/templates/script/tmt.j2
    ln -sr main.fmf ~/.config/tmt/templates/test/tmt.j2
