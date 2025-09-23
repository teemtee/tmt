#!/usr/bin/python3

# Install this file into /usr/lib/python*/site-packages/mockbuild/plugins/tmt.py

import subprocess
import os
import shlex

from pathlib import Path

from mockbuild.exception import Error
from mockbuild.trace_decorator import getLog, traceLog

requires_api_version = "1.1"

# plugin entry point
@traceLog()
def init(plugins, conf, buildroot):
    TmtPlugin(plugins, conf, buildroot)


class TmtPlugin(object):
    """
    Enables tmt to work with mock shell
    """

    @traceLog()
    def __init__(self, plugins, conf, buildroot):
        self.buildroot = buildroot
        self.config = conf
        self.workdir = Path(self.buildroot.basedir).joinpath("workdir").resolve()
        self.workdir_root = None
        self.host_workdir_root = None

        if self.buildroot.bootstrap_buildroot is not None:
            plugins.add_hook("preshell", self.mount_overlay)

        plugins.add_hook("preshell", self.mount_workdir)
        plugins.add_hook("postshell", self.umount_workdir)

        if self.buildroot.bootstrap_buildroot is not None:
            plugins.add_hook("postshell", self.umount_overlay)

    @traceLog()
    def mount_overlay(self):
        self.buildroot.root_log.info("Enabled tmt plugin")
        
        forbidden_prefixes = [
            "/bin",
            "/boot",
            # "/dev",
            "/etc",
            # "/home",
            "/lib",
            "/lib64",
            # "/media",
            # "/mnt",
            # "/opt",
            "/proc",
            # "/root",
            # "/run",
            "/sbin",
            # "/srv",
            "/sys",
            # "/tmp",
            "/usr",
            # "/var",
        ]
        
        for forbidden_prefix in forbidden_prefixes:
            if Path(self.buildroot.basedir).is_relative_to(forbidden_prefix):
                raise Error(f"Refusing to mount overlay in directory: {self.buildroot.basedir}")
        
        # overlay bootstrap chroot into chroot
        subprocess.run(['rm', '-rf', shlex.quote(str(self.workdir))], check = True)
        os.mkdir(self.workdir)
        getLog().info("tmt: overlay-mounting %s at %s", self.buildroot.bootstrap_buildroot.rootdir, self.buildroot.rootdir)
        subprocess.run(["mount", "-t", "overlay", "overlay",
            "-o", f"lowerdir={self.buildroot.bootstrap_buildroot.rootdir}",
            "-o", f"upperdir={self.buildroot.rootdir}",
            "-o", f"workdir={shlex.quote(str(self.workdir))}",
            self.buildroot.rootdir], check = True)
        
    @traceLog()
    def mount_workdir(self):
        self.workdir_root = self.config["workdir_root"]
        self.host_workdir_root = self.buildroot.rootdir + self.workdir_root
        # bind-mount tmt workdir into chroot
        subprocess.run(['rm', '-rf', shlex.quote(str(self.host_workdir_root))], check = True)
        os.mkdir(self.host_workdir_root)
        getLog().info("tmt: bind-mounting %s at %s", self.workdir_root, self.host_workdir_root)
        subprocess.run(["mount", "--bind", shlex.quote(str(self.workdir_root)), shlex.quote(str(self.host_workdir_root))], check = True)
    
    @traceLog()
    def umount_overlay(self):
        getLog().info("tmt: unmounting overlay at %s", self.buildroot.rootdir)
        subprocess.run(["umount", "-l", shlex.quote(str(self.buildroot.rootdir))], check = True)
    
    @traceLog()
    def umount_workdir(self):
        getLog().info("tmt: unmounting bind at %s", self.host_workdir_root)
        subprocess.run(["umount", "-l", shlex.quote(str(self.host_workdir_root))], check = True)
