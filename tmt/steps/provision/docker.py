from pathlib import Path

import click
import tmt


class ProvisionDocker(tmt.steps.provision.ProvisionPlugin):
    """
    Docker provision plugin
    """

    # Guest instance
    _guest = None

    # Supported keys
    _keys = ["image", "container", "pull"]

    # Supported methods
    _methods = [tmt.steps.Method(name="docker", doc=__doc__, order=50)]

    @classmethod
    def options(cls, how=None):
        """ Prepare command line options for connect """
        return [
            click.option(
                "-i",
                "--image",
                metavar="IMAGE",
                help="Select image to use. Short name or complete url.",
            ),
            click.option(
                "-c",
                "--container",
                metavar="NAME",
                help="Name or id of an existing container to be used.",
            ),
            click.option(
                "-p",
                "--pull",
                is_flag=True,
                help="Force pulling a fresh container image.",
            ),
        ] + super().options(how)

    def wake(self, options=None, data=None):
        """ Override options and wake up the guest """
        if data:
            self._guest = GuestDocker(data, name=self.name, parent=self.step)
            self._guest.run_container(self.get("image"))

    def go(self):
        """ Provision the container """
        super().go()
        # Prepare data for the guest instance
        data = dict()
        for key in self._keys:
            data[key] = self.get(key)
        self._guest = GuestDocker(data, name=self.name, parent=self.step)
        self._guest.run_container(
            self.get("image"),
            path=str(Path("/data/tests/integration/inhibit-if-kmods-is-not-supported")),
        )

    def guest(self):
        """ Return the provisioned guest """
        return self._guest

    def requires(self):
        """ List of required packages needed for workdir sync """
        return GuestDocker.requires()

    def show(self):
        """ Show provision details """
        super().show(self._keys)


class GuestDocker(tmt.Guest):
    """ Docker """

    def ansible(self, playbook):
        """ Prepare docker container with ansible playbook """
        playbook = self._ansible_playbook_path(playbook)
        breakpoint()
        stdout, stderr = self.run(
            f"ansible-playbook {self._ansible_verbosity()} "
            f"-c docker -i {self.container}, "
            f"{playbook} "
            f"-vvv"
        )
        self._ansible_summary(stdout)

    def run_container(self, image, path):
        container, _ = self.run(
            f"docker run -itd --workdir={path} {image}",
            message=f"Running container from the image {image}",
        )
        self.container = container.strip()

    def execute(self, command, **kwargs):
        """ Execute command on docker """
        # Change to given directory on guest if cwd provided
        return self.run(f"docker exec {self.container} {command}")

    def push(self):
        pass

    def pull(self):
        pass

    def stop(self):
        self.info("Stopping the container...")
        _, err = self.run(f"docker stop {self.container}")
        if err:
            self.warn(f"Stopping failed.\nDetails: {err}")

    def remove(self):
        self.info("Removing the container...")
        _, err = self.run(f"docker rm -f {self.container}")
        if err:
            self.warn(f"Removing failed.\nDetails: {err}")

    @classmethod
    def requires(cls):
        """ No packages needed to sync workdir """
        return []

    def load(self, data):
        """ Load guest data and initialize attributes """
        super().load(data)

        # Load basic data
        self.image = data.get("image")
        self.force_pull = data.get("pull")
        self.container = None

    def save(self):
        """ Save guest data for future wake up """
        data = {
            "container": self.container,
        }
        return data
