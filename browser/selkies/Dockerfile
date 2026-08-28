# Teddy Downloader — Selkies Wayland Browser
#
# Keep the tested Selkies base immutable. The base owns:
#   - s6 supervision
#   - headless Wayland capture compositor
#   - nested labwc session compositor
#   - LXQt session
#   - PipeWire audio
#   - Intel/AMD VA-API / GPU plumbing
#
# Teddy adds only:
#   - Chrome for Testing
#   - the tracked Teddy Downloader extension
#
# Browser startup/autostart is intentionally installed separately.

FROM ghcr.io/selkies-project/selkies/example@sha256:605439895c47fd2d9ff6ca4d848b95567e8a7730fee1bbc1b8a0e03205cdaa50

ARG CFT_VERSION

USER 0

# Teddy desktop adaptive resolution ceiling.
# Keep Selkies auto-resize enabled, but bound
# desktop stream geometry to 3840x2160.
# The patcher fail-closes unless the pinned
# Selkies frontend matches the verified SHA.
COPY --chown=0:0 --chmod=0755 \
  browser/selkies/patch_selkies_resolution.py \
  /tmp/patch_selkies_resolution.py

RUN /usr/bin/python3 \
      /tmp/patch_selkies_resolution.py && \
    rm -f \
      /tmp/patch_selkies_resolution.py

RUN if [ -z "${CFT_VERSION}" ]; then \
      echo "ERROR: CFT_VERSION build argument is required"; \
      false; \
    fi && \
    mkdir -p /opt/teddy-browser && \
    curl -fL \
      --retry 5 \
      --retry-delay 2 \
      --retry-all-errors \
      "https://storage.googleapis.com/chrome-for-testing-public/${CFT_VERSION}/linux64/chrome-linux64.zip" \
      -o /tmp/teddy-cft.zip && \
    mkdir -p /tmp/teddy-cft && \
    python3 -c 'import os, zipfile; z=zipfile.ZipFile("/tmp/teddy-cft.zip"); z.extractall("/tmp/teddy-cft"); [(lambda p,m: os.chmod(p,m) if m else None)(os.path.join("/tmp/teddy-cft", i.filename), (i.external_attr >> 16) & 0o7777) for i in z.infolist() if os.path.exists(os.path.join("/tmp/teddy-cft", i.filename))]' && \
    mv /tmp/teddy-cft/chrome-linux64 /opt/teddy-browser/chrome && \
    rm -rf /tmp/teddy-cft /tmp/teddy-cft.zip && \
    chown -R 1000:1000 /opt/teddy-browser/chrome && \
    ln -s /opt/teddy-browser/chrome/chrome /usr/local/bin/teddy-chrome

RUN mkdir -p /etc/opt/chrome_for_testing/policies/managed

COPY --chown=0:0 --chmod=0644 \
  browser/selkies/teddy-chrome-policy.json \
  /etc/opt/chrome_for_testing/policies/managed/teddy-browser.json

COPY --chown=1000:1000 \
  deploy/vpn-browser-extension/ \
  /opt/teddy-browser/extension/

COPY --chown=1000:1000 \
  browser/selkies/start-teddy-browser.sh \
  /opt/teddy-browser/start-teddy-browser.sh

COPY --chown=1000:1000 --chmod=0755 \
  browser/selkies/teddy_selkies_control.py \
  /opt/teddy-browser/teddy_selkies_control.py

COPY --chown=1000:1000 --chmod=0755 \
  browser/selkies/teddy-selkies-control-run.sh \
  /etc/service/teddy-selkies-control/run

RUN chown -R 1000:1000 \
  /etc/service/teddy-selkies-control

COPY browser/selkies/teddy-browser.desktop \
  /etc/xdg/autostart/teddy-browser.desktop

RUN install -d -o 1000 -g 1000 -m 0755 /home/ubuntu/.config && \
    install -d -o 1000 -g 1000 -m 0755 /home/ubuntu/.config/autostart

COPY --chown=1000:1000 --chmod=0644 \
  browser/selkies/lxqt-panel.desktop \
  /home/ubuntu/.config/autostart/lxqt-panel.desktop

RUN chmod 0755 /opt/teddy-browser/start-teddy-browser.sh && \
    chmod 0644 /etc/xdg/autostart/teddy-browser.desktop && \
    mkdir -p /config/chrome-profile && \
    chown -R 1000:1000 /config

ENV TEDDY_CHROME_BIN=/opt/teddy-browser/chrome/chrome \
    TEDDY_EXTENSION_DIR=/opt/teddy-browser/extension \
    TEDDY_PROFILE_DIR=/config/chrome-profile

USER 1000

RUN test -x "${TEDDY_CHROME_BIN}" && \
    test -f "${TEDDY_EXTENSION_DIR}/manifest.json" && \
    test -f "${TEDDY_EXTENSION_DIR}/background.js" && \
    "${TEDDY_CHROME_BIN}" --version

WORKDIR /home/ubuntu

# Preserve the Selkies base image entrypoint.
