# Configuration

All the configuration for building image variants is defined by multiple
config files; the base configs for official Alpine Linux cloud images are in
the [`configs/`](configs/) directory.

We use [HOCON](https://github.com/lightbend/config/blob/main/HOCON.md) for
configuration -- this primarily facilitates importing deeper configs from
other files, but also allows the extension/concatenation of arrays and maps
(which can be a useful feature for customization), and inline comments.

----
## Resolving Work Environment Configs and Scripts

If `work/configs/` and `work/scripts/` don't exist, the `build` script will
install the contents of the base [`configs/`](configs/) and [`scripts/`](scripts/)
directories, and overlay additional `configs/` and `scripts/` subdirectories
from `--custom` directories (if any).

Files cannot be installed over existing files, with one exception -- the
[`configs/images.conf`](configs/images.conf) same-directory symlink.  Because
the `build` script _always_ loads `work/configs/images.conf`, this is the hook
for "rolling your own" custom Alpine Linux cloud images.

The base [`configs/images.conf`](configs/images.conf) symlinks to
[`alpine.conf`](configs/images.conf), but this can be overridden using a
`--custom` directory containing a new `configs/images.conf` same-directory
symlink pointing to its custom top-level config.

For example, the configs and scripts in the [`overlays/testing/`](overlays/testing/)
directory can be resolved in a _clean_ work environment with...
```
./build configs --custom overlays/testing
```
This results in the `work/configs/images.conf` symlink to point to
`work/configs/alpine-testing.conf` instead of `work/configs/alpine.conf`.

If multiple directories are specified with `--custom`, they are applied in
the order given.

----
## Top-Level Config File

Examples of top-level config files are [`configs/alpine.conf`](configs/alpine.conf)
and [`overlays/testing/configs/alpine-testing.conf`](overlays/testing/configs/alpine-testing.conf).

There are three main blocks that need to exist (or be `import`ed into) the top
level HOCON configuration, and are merged in this exact order:

### `Default`

All image variant configs start with this block's contents as a starting point.
Arrays and maps can be appended by configs in `Dimensions` and `Mandatory`
blocks.

### `Dimensions`

The sub-blocks in `Dimensions` define the "dimensions" a variant config is
comprised of, and the different config values possible for that dimension.
The default [`alpine.conf`](configs/alpine.conf) defines the following
dimensional configs:

* `version` - Alpine Linux _x_._y_ (plus `edge`) versions
* `arch` - machine architectures, `x86_64` or `aarch64`
* `firmware` - supports launching via legacy BIOS or UEFI
* `bootstrap` - the system/scripts responsible for setting up an instance
  during its initial launch
* `cloud` - for specific cloud platforms

The specific dimensional configs for an image variant are merged in the order
that the dimensions are listed.

### `Mandatory`

After a variant's dimensional configs have been applied, this is the last block
that's merged to the image variant configuration.  This block is the ultimate
enforcer of any non-overrideable configuration across all variants, and can
also provide the last element to array config items.

----
## Dimensional Config Directives

Because a full cross-product across all dimensional configs may produce images
variants that are not viable (i.e. `aarch64` simply does not support legacy
`bios`), or may require further adjustments (i.e. the `aws` `aarch64` images
require an additional kernel module from `3.15` forward, which aren't available
in previous versions), we have two special directives which may appear in
dimensional configs.

### `EXCLUDE` array

This directive provides an array of dimensional config keys which are
incompatible with the current dimensional config.  For example,
[`configs/arch/aarch64.conf`](configs/arch/aarch64.conf) specifies...
```
# aarch64 is UEFI only
EXCLUDE = [bios]
```
...which indicates that any image variant that includes both `aarch64` (the
current dimensional config) and `bios` configuration should be skipped.

### `WHEN` block

This directive conditionally merges additional configuration ***IF*** the
image variant also includes a specific dimensional config key (or keys).  In
order to handle more complex situations, `WHEN` blocks may be nested.  For
example, [`configs/cloud/aws.conf`](configs/cloud/aws.conf) has...
```
WHEN {
  aarch64 {
    # new AWS aarch64 default...
    kernel_modules.gpio_pl061   = true
    initfs_features.gpio_pl061  = true
    WHEN {
      "3.14 3.13 3.12" {
        # ...but not supported for older versions
        kernel_modules.gpio_pl061   = false
        initfs_features.gpio_pl061  = false
      }
    }
  }
```
This configures AWS `aarch64` images to use the `gpio_pl061` kernel module in
order to cleanly shutdown/reboot instances from the web console, CLI, or SDK.
However, this module is unavailable on older Alpine versions.

Spaces in `WHEN` block keys serve as an "OR" operator; nested `WHEN` blocks
function as "AND" operators.

----
## Config Settings

**Scalar** values can be simply overridden in later configs.

**Array** and **map** settings in later configs are merged with the previous
values, _or entirely reset if it's first set to `null`_, for example...
```
some_array = [ thing ]
# [...]
some_array = null
some_array = [ other_thing ]
```

Mostly in order of appearance, as we walk through
[`configs/alpine.conf`](configs/alpine.conf) and the deeper configs it
imports...

### `project` string

This is a unique identifier for the whole collection of images being built.
For the official Alpine Linux cloud images, this is set to
`https://alpinelinux.org/cloud`.

When building custom images, you **MUST** override **AT LEAST** this setting to
avoid image import and publishing collisions.

### `userhost` string

This is the remote _user_@_host_ that is used for storing state, uploading
files, and releasing official images.  Currently used by `storage_url` and
`release_cmd`.

### `name` array

The ultimate contents of this array contribute to the overall naming of the
resultant image.  Almost all dimensional configs will add to the `name` array,
with two notable exceptions: **version** configs' contribution to this array is
determined when `work/images.yaml` is resolved, and is set to the current
Alpine Linux release (_x.y.z_ or _YYYYMMDD_ for edge); also because
**cloud** images are isolated from each other, it's redundant to include that
in the image name.

### `description` array

Similar to the `name` array, the elements of this array contribute to the final
image description.  However, for the official Alpine configs, only the
**version** dimension adds to this array, via the same mechanism that sets the
revision for the `name` array.

### `motd` map

This setting controls the contents of what ultimately gets written into the
variant image's `/etc/motd` file.  Later configs can add additional messages,
replace existing contents, or remove them entirely (by setting the value to
`null`).

The `motd.release_notes` setting will be ignored if the Alpine release does
not have a release notes web page associated with it.

### `scripts` array

These are the scripts that will be executed by Packer, in order, to do various
setup tasks inside a variant's image.  The `work/scripts/` directory contains
all scripts, including those that may have been added via `build --custom`.

### `script_dirs` array

Directories (under `work/scripts/`) that contain additional data that the
`scripts` will need.  Packer will copy these to the VM responsible for setting
up the variant image.

### `disk_size` array

The sum of this array is the size of the image disk, specified in MiB; this
allows different dimension variants to "bump up" the size of the image if
extra space is needed.

### `image_format` string

The format/extension of the disk image, i.e. `qcow2`, `vhd`, or `raw`.

### `image_format_opts` string

Some formats have additional options; currently `vhd/force-size` and
`vhd/fixed_force-size` are defined.

### `login` string

The image's primary login user, set to `alpine`.

### `repos` map

Defines the contents of the image's `/etc/apk/repositories` file.  The map's
key is the URL of the repo, and the value determines how that URL will be
represented in the `repositories` file...
| value | result |
|-|-|
| `null`  | make no reference to this repo |
| `false` | this repo is commented out (disabled) |
| `true`  | this repo is enabled for use |
| _tag_   | enable this repo with `@`_`tag`_ |

### `packages` map

Defines what APK packages to add/delete.  The map's key is the package
name, and the value determines whether (or not) to install/uninstall the
package...
| value | result |
|-|-|
| `null`               | don't add or delete |
| `false`              | explicitly delete |
| `true`               | add from default repos |
| _tag_                | add from `@`_`tag`_ repo |
| `--no-scripts`       | add with `--no-scripts` option |
| `--no-scripts` _tag_ | add from `@`_`tag`_ repo, with `--no-scripts` option |

### `services` map of maps

Defines what services are enabled/disabled at various runlevels.  The first
map's key is the runlevel, the second key is the service.  The service value
determines whether (or not) to enable/disable the service at that runlevel...
| value   | result |
|-|-|
| `null`  | don't enable or disable |
| `false` | explicitly disable |
| `true`  | explicitly enable |

### `kernel_modules` map

Defines what kernel modules are specified in the boot loader.  The key is the
kernel module, and the value determines whether or not it's in the final
list...
| value   | result |
|-|-|
| `null`  | skip |
| `false` | skip |
| `true`  | include |

### `kernel_options` map

Defines what kernel options are specified on the kernel command line.  The keys
are the kernel options, the value determines whether or not it's in the final
list...
| value   | result |
|-|-|
| `null`  | skip |
| `false` | skip |
| `true`  | include |

### `initfs_features` map

Defines what initfs features are included when making the image's initramfs
file.  The keys are the initfs features, and the values determine whether or
not they're included in the final list...
| value   | result |
|-|-|
| `null`  | skip |
| `false` | skip |
| `true`  | include |

### `qemu.machine_type` string

The QEMU machine type to use when building local images.  For x86_64, this is
set to `null`, for aarch64, we use `virt`.

### `qemu.args` list of lists

Additional QEMU arguments.  For x86_64, this is set to `null`; but aarch64
requires several additional arguments to start an operational VM.

### `qemu.firmware` string

The path to the QEMU firmware (installed in `work/firmware/`).  This is only
used when creating UEFI images.

### `bootloader` string

The bootloader to use, currently `extlinux` or `grub-efi`.

### `access` map

When images are published, this determines who has access to those images.
The key is the cloud account (or `PUBLIC`), and the value is whether or not
access is granted, `true` or `false`/`null`.

### `regions` map

Determines where images should be published.  The key is the region
identifier (or `ALL`), and the value is whether or not to publish to that
region, `true` or `false`/`null`.

### `encrypted` string

Determines whether the image will be encrypted when imported and published.
Currently, only the **aws** cloud module supports this.

### `repo_keys` array

List of addtional repository keys to trust during the package installation phase.
This allows pulling in custom apk packages by simple specifying the repository name in packages block.

### `storage_url` string

This is an URL that defines where the persistent state about images is stored,
from `upload` through `release` steps (and beyond).  This allows one `build`
session to pick up where another left off.  Currently, `ssh://` and `file://`
URLs are supported.

### `download_url` string

This string is used for building download URLs for officially released images
on the https://alpinelinux.org/cloud web page.

### `signing_cmd` string

Command template to cryptographically sign files.

### `release_cmd` string

Command template to complete the release of an image.
