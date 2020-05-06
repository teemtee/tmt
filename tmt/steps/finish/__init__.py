import re
import fmf
import tmt
import click


class Finish(tmt.steps.Step):
    """
    Perform the finishing tasks and clean up provisioned guests

    Additional actions to be performed after the test execution has been
    completed. Counterpart of the ``prepare`` step useful for various
    cleanup actions. Also takes care of stopping and removing guests.

    Note that the ``finish`` step is also run when any of the previous
    steps failed (for example when the environment preparation was not
    successful) so that provisioned systems are not kept running.
    """

    def wake(self):
        """ Wake up the step (process workdir and command line) """
        super().wake()

        # Choose the right plugin and wake it up
        for data in self.data:
            plugin = FinishPlugin.delegate(self, data)
            plugin.wake()
            # Add plugin only if there are data
            if len(plugin.data.keys()) > 2:
                self._plugins.append(plugin)

        # Nothing more to do if already done
        if self.status() == 'done':
            self.debug(
                'Finish wake up complete (already done before).', level=2)
        # Save status and step data (now we know what to do)
        else:
            self.status('todo')
            self.save()

    def show(self):
        """ Show finish details """
        for data in self.data:
            FinishPlugin.delegate(self, data).show()

    def summary(self):
        """ Give a concise summary """
        tasks  = fmf.utils.listed(self.plugins(), 'task')
        self.info('summary', f'{tasks} completed', 'green', shift=1)

    def go(self):
        """ Execute finishing tasks """
        super().go()

        available_guests = self.plan.provision.guests()

        # Nothing more to do if already done
        if self.status() == 'done':
            if not available_guests:
                self.info('status', 'done', 'green', shift=1)
                self.summary()
                return
        else:
            # Go and execute each plugin on all guests
            for guest in available_guests:
                for plugin in self.plugins():
                    plugin.go(guest)

        if available_guests and self.opt('keep'):
            self.info("Guest will keep running", shift=1)
            self.info("Run `tmt run --id {} finish` later to finish properly".format(self.parent.run.workdir), shift=1)

        for guest in available_guests:
            if self.opt('keep'):
                # Print details about connection
                self.info("guest", guest.name, color='magenta', shift=1)
                self.info('connect', "ssh {} {}".format(guest._ssh_guest(), guest._ssh_options(True)), 'green', shift=1)
            else:
                # Stop and remove provisioned guests
                guest.stop()
                guest.remove()

        # Give a summary, update status and save
        self.summary()
        self.status('done')
        self.save()


class FinishPlugin(tmt.steps.Plugin):
    """ Common parent of finish plugins """

    # List of all supported methods aggregated from all plugins
    _supported_methods = []

    @classmethod
    def base_command(cls, method_class=None, usage=None):
        """ Create base click command (common for all finish plugins) """

        # Prepare general usage message for the step
        if method_class:
            usage = Finish.usage(method_overview=usage)

        # Create the command
        @click.command(cls=method_class, help=usage)
        @click.pass_context
        @click.option(
            '-h', '--how', metavar='METHOD',
            help='Use specified method for finishing tasks.')
        @click.option(
            '--keep', is_flag=True,
            help='Keep guests running in the end.')
        def finish(context, **kwargs):
            context.obj.steps.add('finish')
            Finish._save_context(context)

        return finish
