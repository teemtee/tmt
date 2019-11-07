# coding: utf-8

""" Provision Step Classes """

import tmt

from click import echo

from tmt.utils import SpecificationError


class Provision(tmt.steps.Step):
    """ Provision step """

    # Default implementation for provision is a virtual machine
    how = 'virtual'

    def __init__(self, data, plan):
        super(Provision, self).__init__(data, plan)
        # List of provisioned guests
        self.guests = []

    def wake(self):
        """ Wake up the step (process workdir and command line) """
        super(Provision, self).wake()
        image = self.opt('image')
        # Choose the plugin
        for data in self.data:
            how = data.get('how')
            # Update the image if provided
            if image is not None:
                data['image'] = image
            if how == 'local':
                from .localhost import ProvisionLocalhost
                self.guests.append(ProvisionLocalhost(data, self))
            else:
                from .vagrant import ProvisionVagrant
                self.guests.append(ProvisionVagrant(data, self))

    def go(self):
        """ Provision all resources """
        super(Provision, self).go()

        for guest in self.guests:
            guest.go()
            guest.save()

    def execute(self, *args, **kwargs):
        for guest in self.guests:
            guest.execute(*args, **kwargs)

    def load(self):
        for guest in self.guests:
            guest.load()

    def save(self):
        for guest in self.guests:
            guest.save()

    def show(self):
        """ Show provision details """
        keys = ['how', 'image']
        super(Provision, self).show(keys)

    def sync_workdir_to_guest(self):
        for guest in self.guests:
            guest.sync_workdir_to_guest()

    def sync_workdir_from_guest(self):
        for guest in self.guests:
            guest.sync_workdir_from_guest()

    def copy_from_guest(self, target):
        for guest in self.guests:
            guest.copy_from_guest(target)

    def destroy(self):
        for guest in self.guests:
            guest.destroy()

    def prepare(self, how, what):
        for guest in self.guests:
            guest.prepare(how, what)

    def clean(self):
        for guest in self.guests:
            guest.clean()
