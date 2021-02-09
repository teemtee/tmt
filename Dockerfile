FROM registry.fedoraproject.org/fedora

# For root user
RUN set -x && \
  mkdir -p /run/

COPY plans/main.fmf /run/plans/
COPY .fmf/ /run/.fmf

# In case someone needs regular user
ENV HOME_DIR /home/test

RUN set -x && \
  mkdir -p $HOME_DIR/run/

COPY plans/main.fmf $HOME_DIR/run/plans/
COPY .fmf/ $HOME_DIR/run/.fmf

RUN set -x && \
  dnf install -y --setopt=tsflags=nodocs \
    tmt-all beakerlib && \
  dnf clean all --enablerepo='*' && \
  useradd -u 1001 test && \
  chown -R test:test $HOME_DIR && \
  echo 'test ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

# USER 1001
# Run as root by default
# WORKDIR $HOME_DIR/run

WORKDIR /run

CMD tmt run -av provision -h local
