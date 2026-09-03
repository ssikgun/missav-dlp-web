# Stage10-B4 separate guarded apply deployment plan

Planning artifact only.  This checkpoint does not install files, reload
systemd, create a timer, or enable automatic apply.

## Runtime UPDATE

- `/opt/missav-dlp-web/stage9-runtime/teddy_discovery_jav_reconcile.py`
  - add bounded writer-lock support, latest-DB revalidation, and post-apply
    integrity/semantic verification
- `/opt/missav-dlp-web/stage9-runtime/teddy_discovery_organizer_apply.py`
  - preserve existing blocking lock behavior and add optional bounded lock
    acquisition

## Runtime ADD

- `/opt/missav-dlp-web/stage9-runtime/teddy_discovery_jav_reconcile_apply.py`
  - strict allowlist apply entrypoint

## Wrapper ADD

- `/usr/local/sbin/teddy-discovery-jav-reconcile-apply`
  - source: `deploy/systemd/teddy-discovery-jav-reconcile-apply`

## Service ADD

- `/etc/systemd/system/teddy-discovery-jav-reconcile-apply.service`
  - source: `deploy/systemd/teddy-discovery-jav-reconcile-apply.service`
  - `Type=oneshot`, exact runtime/DB/JAV root, existing
    `/etc/default/teddy-discovery`, writer-lock bound of two seconds, and no
    `Restart=` policy

No apply timer is part of this manifest.  The existing
`teddy-discovery-jav-reconcile.service` and timer remain report-only and are
unchanged.

## Rollback targets

- Remove the added apply runtime module, wrapper, and service.
- Restore the previous `teddy_discovery_jav_reconcile.py` and
  `teddy_discovery_organizer_apply.py` runtime files from the deployment
  backup.
- Leave the existing report-only service and timer in their pre-deployment
  state; do not stop, disable, or convert them as part of this plan.
