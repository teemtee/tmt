FROM quay.io/centos-bootc/centos-bootc:stream9

RUN dnf -y install cloud-init rsync && \
    ln -s ../cloud-init.target /usr/lib/systemd/system/default.target.wants && \
    rm /usr/local -rf && ln -sr /var/usrlocal /usr/local && mkdir -p /var/usrlocal/bin && \
    dnf clean all
