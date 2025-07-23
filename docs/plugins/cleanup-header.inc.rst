The :ref:`/spec/plans/cleanup` step plugins implement cleanup
actions to be performed at the very end of testing.

Stop and remove all guests after the testing is finished. Also takes
care of pruning irrelevant files and directories from the workdir so
that we do not eat up unnecessary disk space after everything is
done.

Note that the ``cleanup`` step is also run when any of the previous
steps failed (for example when the environment preparation was not
successful) so that provisioned systems are not kept running and
consuming resources.
