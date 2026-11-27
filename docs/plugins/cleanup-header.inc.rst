The :tmt:story:`/spec/plans/cleanup` step plugins release resources
at the end of testing.

The :ref:`/plugins/cleanup/tmt` plugin stops and removes provisioned
guests and prunes unneeded files from the run workdir.

.. note::
    Note that the ``cleanup`` step is also run when any of the previous
    steps failed (for example when the environment preparation was not
    successful) so that provisioned systems are not kept running and
    consuming resources.

The default method is :ref:`tmt </plugins/cleanup/tmt>`.
