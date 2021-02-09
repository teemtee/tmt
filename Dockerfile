FROM registry.fedoraproject.org/fedora

ENV HOME /home/test

RUN set -x && \
  mkdir -p $HOME/run/

COPY plans/main.fmf $HOME/run/plans/
COPY .fmf/ $HOME/run/.fmf

RUN set -x && \
  dnf install -y --setopt=tsflags=nodocs \
    tmt-all beakerlib && \
  dnf clean all --enablerepo='*' && \
  useradd -u 1001 test && \
  chown -R test:test $HOME && \
  echo 'test ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

USER 1001

WORKDIR $HOME/run

#RUN tmt init && tmt run | grep -E '^total: 4 tests passed$'
CMD tmt run -v
