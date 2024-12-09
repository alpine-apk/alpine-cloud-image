# TODO

## SOON-ish

* do we still need to put `interfaces` into the image, or will Tiny Cloud and
  cloud-init handle it?  _(seems to be so, but need to test)_

* do we still need to set `ntp_server` for AWS images, starting with 3.18.4?

  **NOTE:** This is left unset for 3.21.0 -
  _(default config for `chrony` uses `pool.ntp.org`)_

* `generic` cloud should result in multiple formats -- implement
  `image_formats` array/map in parallel (or instead of `image_format`, etc.)

## LATER

* support `<` and `>` in `EXCLUDE` and `WHEN` blocks for version comparison

* stop making BIOS images by default (or entirely?)
  * switch to UEFI only ***OR***...
  * ...figure out how to do hybrid BIOS/UEFI images

* consider separating official Alpine Linux configuration into an overlay
  to be applied via `--custom`.

* figure out rollback / `refresh_state()` for images that are already signed,
  don't sign again unless directed to do so.
