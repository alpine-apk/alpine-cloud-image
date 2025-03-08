# Alpine Linux Cloud Image Builder

This repository contains the code and and configs for the build system used to
create official Alpine Linux images for various cloud providers, in various
configurations.  This build system is flexible, enabling others to build their
own customized images.

----
## Pre-Built Offical Cloud Images

To get started with offical pre-built Alpine Linux cloud images, visit
https://alpinelinux.org/cloud.  Currently, we build official images for the
following cloud platforms...
* Amazon Web Services (AWS)
* Microsoft Azure
* GCP (Google Cloud Platform)
* OCI (Oracle Cloud Infrastructure)
* NoCloud

Each image's name contains the Alpine version release, architecture, firmware,
bootstrap, and image revision; a YAML metadata file containing these details
and more is downloadable.

| Key | Description / Values |
|-----|----------------------|
| name | `alpine-`_`release`_`-`_`arch`_`-`_`firmware`_`-`_`bootstrap`_`-r`_`revision`_ |
| project | `https://alpinelinux.org/cloud` |
| image_key | _`release`_`-`_`arch`_`-`_`firmware`_`-`_`bootstrap`_`-`_`cloud`_ |
| version | Alpine version (_`x.y`_ or `edge`) |
| release | Alpine release (_`x.y.z`_ or _`YYYYMMDD`_ for edge) |
| arch | architecture (`aarch64` or `x86_64`) |
| firmware | boot mode (`bios` or `uefi`) |
| bootstrap | initial bootstrap system (`tiny` = Tiny Cloud) |
| cloud | provider short name (`aws`) |
| revision | image revision number |
| built | image build timestamp |
| uploaded | image storage timestamp |
| imported | image import timestamp |
| import_id | imported image id |
| import_region | imported image region |
| signed | image signing timestamp |
| published | image publication timestamp |
| released | image release timestamp _(won't be set until second publish)_ |
| description | image description |

Published AWS images are also tagged with this data, but other AWS accounts
can't read these tags.  However, the image name can still be used to filter
images to find what you're looking for.  For example, to get a list of
available Alpine 3.x aarch64 images in AWS eu-west-2...
```
aws ec2 describe-images \
  --region eu-west-2 \
  --owners 538276064493 \
  --filters \
    Name=name,Values='alpine-3.*-aarch64-*' \
    Name=state,Values=available \
  --output text \
  --query 'reverse(sort_by(Images, &CreationDate))[].[ImageId,Name,CreationDate]'
```
To get just the most recent matching image, use...
```
  --query 'max_by(Image, &CreationDate).[ImageId,Name,CreationDate]'
```

----
## Build System

The build system consists of a number of components:

* the primary `build` script, and other related libraries...
  * `clouds/` - specific cloud provider plugins
  * `alpine.py` - for getting the latest Alpine information
  * `image_config_manager.py` - manages collection of image configs
  * `image_config.py` - individual image config functionality
  * `image_storage.py` - persistent image/metadata storage
  * `image_tags.py` - classes for working with image tags

* the `configs/` directory, defining the set of images to be built

* the `scripts/` directory, containing scripts and related data used to set up
  image contents during provisioning

* the Packer `alpine.pkr.hcl`, which orchestrates the various build steps
  from `local` and beyond.

* the `cloud_helper.py` script that Packer runs in order to do cloud-specific
  per-image operations, such as image format conversion, upload, publishing,
  etc.

### Build Requirements

* [Python](https://python.org) (3.9.9 is known to work)
* [Packer](https://packer.io) (1.9.4 is known to work)
* [QEMU](https://www.qemu.org) (8.1.2 is known to work)
* cloud provider account(s) _(for import/publish steps)_

### Cloud Credentials

Importing and publishing images relies on the cloud providers' Python API
libraries to find and use the necessary credentials, usually via configuration
under the user's home directory (i.e. `~/.aws/`, `~/.oci/`, etc.) or or via
environment variables (i.e. `AWS_...`, `OCI_...`, etc.)

_Note that presently, importing and publishing to cloud providers is only
supported for AWS images._

The credentials' user/role needs sufficient permission to query, import, and
publish images -- the exact details will vary from cloud to cloud.  _It is
recommended that only the minimum required permissions are granted._

_We manage the credentials for publishing official Alpine images with an
"identity broker" service, and retrieve those credentials via the
`--use-broker` argument of the `build` script._

### The `build` Script

```
usage: build [-h] [--debug] [--clean] [--pad-uefi-bin-arch ARCH [ARCH ...]]
         [--custom DIR [DIR ...]] [--skip KEY [KEY ...]] [--only KEY [KEY ...]]
         [--revise] [--use-broker] [--no-color] [--parallel N]
         [--vars FILE [FILE ...]]
         {configs,state,rollback,local,upload,import,sign,publish,release}

positional arguments:   (build up to and including this step)
  configs   resolve image build configuration
  state     report current build state of images
  rollback  remove local/uploaded/imported images if not published or released
  local     build images locally
  upload    upload images and metadata to storage
* import    import local images to cloud provider default region (*)
  sign      cryptographically sign images
* publish   set image permissions and publish to cloud regions (*)
  release   mark images as being officially relased

(*) may not apply to or be implemented for all cloud providers

optional arguments:
  -h, --help                show this help message and exit
  --debug                   enable debug output
  --clean                   start with a clean work environment
  --pad-uefi-bin-arch ARCH [ARCH ...]
                            pad out UEFI firmware to 64 MiB ('aarch64')
  --custom DIR [DIR ...]    overlay custom directory in work environment
  --skip KEY [KEY ...]      skip variants with dimension key(s)
  --only KEY [KEY ...]      only variants with dimension key(s)
  --revise                  bump revision and rebuild if published or released
  --use-broker              use the identity broker to get credentials
  --no-color                turn off Packer color output
  --parallel N              build N images in parallel
  --vars FILE [FILE ...]    supply Packer with -vars-file(s) (default: [])
  --disable STEP [STEP ...] disable optional steps (default: [])
```

The `build` script will automatically create a `work/` directory containing a
Python virtual environment if one does not already exist.  This directory also
hosts other data related to building images.  The `--clean` argument will
remove everything in the `work/` directory except for things related to the
Python virtual environment.

If `work/configs/` or `work/scripts/` directories do not yet exist, they will
be populated with the base configuration and scripts from `configs/` and/or
`scripts/` directories.  If any custom overlay directories are specified with
the `--custom` argument, their `configs/` and `scripts/` subdirectories are
also added to `work/configs/` and `work/scripts/`.

The "build step" positional argument deterimines the last step the `build`
script should execute -- all steps before this targeted step may also be
executed.  That is, `build local` will first execute the `configs` step (if
necessary) and then the `state` step (always) before proceeding to the `local`
step.

The `configs` step resolves configuration for all buildable images, and writes
it to `work/images.yaml`, if it does not already exist.

The `state` step always checks the current state of the image builds,
determines what actions need to be taken, and updates `work/images.yaml`.  A
subset of image builds can be targeted by using the `--skip` and `--only`
arguments.

The `rollback` step will remove any imported, uploaded, or local images, but
only if they are _unpublished_ and _unreleased_.

As _published_ and _released_ images can't be rolled back, `--revise` can be
used to increment the _`revision`_ value to rebuild newly revised images.

`local`, `upload`, `import`, `publish`, `sign` , and `release` steps are
orchestrated by Packer.  By default, each image will be processed serially;
providing the `--parallel` argument with a value greater than 1 will
parallelize operations.  The degree to which you can parallelize `local` image
builds will depend on the local build hardware -- as QEMU virtual machines are
launched for each image being built.  Image `upload`, `import`, `publish`,
`sign`, and `release` steps are much more lightweight, and can support higher
parallelism.

The `local` step builds local images with QEMU, for those that are not already
built locally or have already been imported.  Images are converted to formats
amenable for import into the cloud provider (if necessary) and checksums are
generated.

The `upload` step uploads the local image, checksum, and metadata to the
defined `storage_url`.  The `import`, `publish`, and `release` steps will
also upload updated image metadata.

The `import` step imports the local images into the cloud providers' default
regions, unless they've already been imported.  At this point the images are
not available publicly, allowing for additional testing prior to publishing.

The `sign` step will cryptographically sign the built image, using the command
specified by the `signing_cmd` config value.

The `publish` step copies the image from the default region to other regions,
if they haven't already been copied there.  This step will always update
image permissions, descriptions, tags, and deprecation date (if applicable)
in all regions where the image has been published.

***NOTE:***  The `import` and `publish` steps are skipped for those cloud
providers where this does not make sense (i.e.  NoCloud) or for those which
it has not yet been coded.

The `release` step simply marks the images as being fully released.  If there
is a `release_cmd` specified, this is also executed, per image.  _(For the
offical Alpine releases, we have a `gen_mksite_release.py` script to convert
the image data to a format that can be used by https://alpinelinux.org/cloud.)_

### The `cloud_helper.py` Script

This script is meant to be called only by Packer from its `post-processor`
block.

----
## Build Configuration

For more in-depth information about how the build system configuration works,
how to create custom config overlays, and details about individual config
settings, see [CONFIGURATION.md](CONFIGURATION.md).
