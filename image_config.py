# vim: ts=4 et:

import mergedeep
import os
import pyhocon
import shutil

from copy import deepcopy
from datetime import datetime
from pathlib import Path

import clouds
from image_storage import ImageStorage, run
from image_tags import ImageTags


class ImageConfig():

    CONVERT_CMD = {
        'qcow2': 'ln -f {opts} {src} {dst}',
        'vhd': 'qemu-img convert -f qcow2 -O vpc {opts} {src} {dst}',
        # NOTE: resizes to 1G,
        'raw.tar.gz' : 'qemu-img convert -f qcow2 -O raw {opts} {src} disk.raw && qemu-img resize -f raw disk.raw 1G && gtar --format=oldgnu -zcvf {dst} disk.raw && rm disk.raw'
    }
    CONVERT_OPTS = {
        None: '',
        'vhd/fixed_force-size': '-o subformat=fixed,force_size',    # TODO: can this work for AWS too?
        'vhd/force-size': '-o force_size=on',
    }
    COMPRESS_CMD = {
        'bz2': ['bzip2', '-c']
    }
    DECOMPRESS_CMD = {
        'bz2': ['bzip2', '-dc']
    }
    # these tags may-or-may-not exist at various times
    OPTIONAL_TAGS = [
        'built', 'uploaded', 'imported', 'import_id', 'import_region',
        'signed', 'published', 'released'
    ]
    STEPS = [
        'local', 'upload', 'import', 'sign', 'publish', 'release'
    ]
    # we expect these to be available
    DEFAULT_OBJ = {
        'built': None,
        'uploaded': None,
        'imported': None,
        'signed': None,
        'published': None,
        'released': None,
        'artifacts': None,
    }

    def __init__(self, config_key, obj={}, log=None, yaml=None):
        self._log = log
        self._yaml = yaml
        self._storage = None
        self.config_key = str(config_key)
        tags = obj.pop('tags', None)
        self.__dict__ |= self.DEFAULT_OBJ | self._deep_dict(obj)
        # ensure tag values are str() when loading
        if tags:
            self.tags = tags

    @classmethod
    def to_yaml(cls, representer, node):
        d = {}
        for k in node.__dict__:
            # don't serialize attributes starting with _
            if k.startswith('_'):
                continue

            d[k] = node.__getattribute__(k)

        return representer.represent_mapping('!ImageConfig', d)

    @property
    def v_version(self):
        return 'edge' if self.version == 'edge' else 'v' + self.version

    @property
    def local_dir(self):
        return Path('work/images') / self.cloud / self.image_key

    @property
    def local_image(self):
        return self.local_dir / ('image.qcow2')

    @property
    def image_name(self):
        return self.name.format(**self.__dict__)

    @property
    def image_description(self):
        return self.description.format(**self.__dict__)

    @property
    def image_file(self):
        return '.'.join([self.image_name, self.image_format])

    @property
    def image_path(self):
        return self.local_dir / self.image_file

    @property
    def metadata_file(self):
        return '.'.join([self.image_name, 'yaml'])

    def region_url(self, region, image_id):
        return self.cloud_region_url.format(region=region, image_id=image_id, **self.__dict__)

    def launch_url(self, region, image_id):
        return self.cloud_launch_url.format(region=region, image_id=image_id, **self.__dict__)

    @property
    def tags(self):
        # stuff that really ought to be there
        t = {
            'arch': self.arch,
            'bootstrap': self.bootstrap,
            'cloud': self.cloud,
            'description': self.image_description,
            'end_of_life': self.end_of_life,
            'firmware': self.firmware,
            'image_key': self.image_key,
            'name': self.image_name.replace(self.cloud + '_', '', 1),
            'project': self.project,
            'release': self.release,
            'revision': self.revision,
            'version': self.version
        }
        # stuff that might not be there yet
        for k in self.OPTIONAL_TAGS:
            if self.__dict__.get(k, None):
                t[k] = self.__dict__[k]

        return ImageTags(t)

    # recursively convert a ConfigTree object to a dict object
    def _deep_dict(self, layer):
        obj = deepcopy(layer)
        if isinstance(layer, pyhocon.ConfigTree):
            obj = dict(obj)

        try:
            for key, value in layer.items():
                # some HOCON keys are quoted to preserve dots
                if '"' in key:
                    obj.pop(key)
                    key = key.strip('"')

                # version values were HOCON keys at one point, too
                if key == 'version' and '"' in value:
                    value = value.strip('"')

                obj[key] = self._deep_dict(value)
        except AttributeError:
            pass

        return obj

    def _merge(self, obj={}):
        mergedeep.merge(self.__dict__, self._deep_dict(obj), strategy=mergedeep.Strategy.ADDITIVE)

    def _get(self, attr, default=None):
        return self.__dict__.get(attr, default)

    def _pop(self, attr, default=None):
        return self.__dict__.pop(attr, default)

    # make data ready for Packer ingestion
    def _normalize(self):
        # stringify arrays
        self.name = '-'.join(self.name)
        self.description = ' '.join(self.description)
        self.repo_keys = ' '.join(self.repo_keys)
        self._resolve_disk_size()
        self._resolve_motd()
        self._resolve_urls()
        self._stringify_repos()
        self._stringify_packages()
        self._stringify_services()
        self._stringify_dict_keys('kernel_modules', ',')
        self._stringify_dict_keys('kernel_options', ' ')
        self._stringify_dict_keys('initfs_features', ' ')

    def _resolve_disk_size(self):
        self.disk_size = str(sum(self.disk_size)) + 'M'

    def _resolve_motd(self):
        # merge release notes, as apporpriate
        if 'release_notes' not in self.motd or not self.release_notes:
            self.motd.pop('release_notes', None)

        motd = {}
        for k, v in self.motd.items():
            if v is None:
                continue

            # join list values with newlines
            if type(v) is list:
                v = "\n".join(v)

            motd[k] = v

        self.motd = '\n\n'.join(motd.values()).format(**self.__dict__)

    def _resolve_urls(self):
        if 'storage_url' in self.__dict__:
            self.storage_url = self.storage_url.format(v_version=self.v_version, **self.__dict__)

        if 'download_url' in self.__dict__:
            self.download_url = self.download_url.format(v_version=self.v_version, **self.__dict__)

    def _stringify_repos(self):
        # stringify repos map
        #   <repo>: <tag>   # @<tag> <repo> enabled
        #   <repo>: false   # <repo> disabled (commented out)
        #   <repo>: true    # <repo> enabled
        #   <repo>: null    # skip <repo> entirely
        #   ...and interpolate {version}
        self.repos = "\n".join(filter(None, (
            f"@{v} {r}" if isinstance(v, str) else
            f"#{r}" if v is False else
            r if v is True else None
            for r, v in self.repos.items()
        ))).format(version=self.version)

    def _stringify_packages(self):
        # resolve/stringify packages map
        #   <pkg>: true                 # add <pkg>
        #   <pkg>: <tag>                # add <pkg>@<tag>
        #   <pkg>: --no-scripts         # add --no-scripts <pkg>
        #   <pkg>: --no-scripts <tag>   # add --no-scripts <pkg>@<tag>
        #   <pkg>: false                # del <pkg>
        #   <pkg>: null                 # skip explicit add/del <pkg>
        pkgs = {'add': '', 'del': '', 'noscripts': ''}
        for p, v in self.packages.items():
            k = 'add'
            if isinstance(v, str):
                if '--no-scripts' in v:
                    k = 'noscripts'
                    v = v.replace('--no-scripts', '')
                v = v.strip()
                if len(v):
                    p += f"@{v}"
            elif v is False:
                k = 'del'
            elif v is None:
                continue

            pkgs[k] = p if len(pkgs[k]) == 0 else pkgs[k] + ' ' + p

        self.packages = pkgs

    def _stringify_services(self):
        # stringify services map
        #   <level>:
        #       <svc>: true     # enable <svc> at <level>
        #       <svc>: false    # disable <svc> at <level>
        #       <svc>: null     # skip explicit en/disable <svc> at <level>
        self.services = {
            'enable': ' '.join(filter(lambda x: not x.endswith('='), (
                '{}={}'.format(lvl, ','.join(filter(None, (
                    s if v is True else None
                    for s, v in svcs.items()
                ))))
                for lvl, svcs in self.services.items()
            ))),
            'disable': ' '.join(filter(lambda x: not x.endswith('='), (
                '{}={}'.format(lvl, ','.join(filter(None, (
                    s if v is False else None
                    for s, v in svcs.items()
                ))))
                for lvl, svcs in self.services.items()
            )))
        }

    def _stringify_dict_keys(self, d, sep):
        self.__dict__[d] = sep.join(filter(None, (
            m if v is True else None
            for m, v in self.__dict__[d].items()
        )))

    def _is_step_or_earlier(self, s, step):
        log = self._log
        if step == 'state':
            return True

        if step not in self.STEPS:
            return False

        return self.STEPS.index(s) <= self.STEPS.index(step)

    def load_local_metadata(self):
        metadata_path = self.local_dir / self.metadata_file
        if metadata_path.exists():
            self._log.debug('Loading image metadata from %s', metadata_path)
            loaded = self._yaml.load(metadata_path)
            loaded.pop('name', None)    # don't overwrite 'name' format string!
            loaded.pop('Name', None)    # remove special AWS tag
            self.__dict__ |= loaded

    def refresh_state(self, step, disable=[], revise=False):
        log = self._log
        actions = {}
        undo = {}

        # enable initial set of possible actions based on specified step
        for s in self.STEPS:
            if self._is_step_or_earlier(s, step) and s not in disable:
                actions[s] = True

        # sets the latest revision metadata (from storage and local)
        self.load_metadata(step)

        # if we're rolling back, figure out what we need to undo first
        if step == 'rollback':
            if self.released or self.published:
                undo['ROLLBACK_BLOCKED'] = True

            else:
                if self.imported and 'import' in clouds.actions(self):
                    undo['import'] = True
                    self.imported = None

                if self.uploaded:
                    undo['upload'] = True
                    self.uploaded = None

                if self.built and self.local_dir.exists():
                    undo['local'] = True
                    self.built = None

        # handle --revise option, if necessary
        if revise and (self.published or self.released):
            # get rid of old metadata
            (self.local_dir / self.metadata_file).unlink()
            self.revision = int(self.revision) + 1
            self.__dict__ |= self.DEFAULT_OBJ
            self.__dict__.pop('import_id', None)
            self.__dict__.pop('import_region', None)

            # do we already have it built locally?
            if self.image_path.exists():
                # then we should use its metadata
                self.load_local_metadata()

            else:
                undo['local'] = True

        # after all that, let's figure out what's to be done!
        if self.built:
            actions.pop('local', None)

        if self.uploaded:
            actions.pop('upload', None)

        if self.imported or 'import' not in clouds.actions(self):
            actions.pop('import', None)

        # NOTE: always publish (if cloud allows) to support new regions
        if 'publish' not in clouds.actions(self):
            actions.pop('publish', None)

        # don't re-publish again if we're targeting the release step
        elif step == 'release' and self.published:
            actions.pop('publish', None)

        # remove remaining actions not possible based on specified step
        for s in self.STEPS:
            if not self._is_step_or_earlier(s, step):
                actions.pop(s, None)

        self.actions = list(actions)
        log.info('%s/%s = [%s]', self.cloud, self.image_name, ' '.join(self.actions))

        if undo:
            act = "Would undo" if step == 'state' else "Undoing"
            log.warning('%s: [%s]', act, ' '.join(undo.keys()))

        if step != 'state':
            if 'import' in undo:
                log.warning('Deleting imported image: %s', self.import_id)
                clouds.delete_image(self, self.import_id)
                self.import_id = None
                self.import_region = None

            if 'upload' in undo:
                log.warning('Removing uploaded image from storage')
                self.remove_image()

            if 'local' in undo:
                log.warning('Removing local build directory')
                shutil.rmtree(self.local_dir)

        self.state_updated = datetime.utcnow().isoformat()

    @property
    def storage(self):
        if self._storage is None:
            self._storage = ImageStorage(self.local_dir, self.storage_url, log=self._log)

        return self._storage

    @property
    def convert_opts(self):
        if 'image_format_opts' in self.__dict__:
            return self.CONVERT_OPTS[self.image_format_opts]

        return ''

    # convert local QCOW2 to format appropriate for a cloud
    def convert_image(self):
        self._log.info('Converting %s to %s', self.local_image, self.image_path)
        run(
            self.CONVERT_CMD[self.image_format].format(opts=self.convert_opts, src=self.local_image, dst=self.image_path),
            log=self._log, errmsg='Unable to convert %s to %s',
            errvals=[self.local_image, self.image_path],
            shell=True
        )
        #self._save_checksum(self.image_path)
        self.built = datetime.utcnow().isoformat()

    def upload_image(self):
        self.storage.store(self.image_file, checksum=True)
        self.uploaded = datetime.utcnow().isoformat()

    def retrieve_image(self):
        self._log.info('Retrieving %s from storage', self.image_file)
        self.storage.retrieve(self.image_file) #, checksum=True)

    def remove_image(self):
        self.storage.remove(
            #self.image_file + '*',
            #self.metadata_file + '*')
            self.image_file,
            self.image_file + '.asc',
            self.image_file + '.sha512',
            self.metadata_file,
            self.metadata_file + '.sha512'
        )

    def sign_image(self):
        log = self._log
        if 'signing_cmd' not in self.__dict__:
            log.warning("No 'signing_cmd' set, not signing image.")
            return

        cmd = self.signing_cmd.format(file=self.image_path).split(' ')
        log.info(f'Signing {self.image_file}...')
        log.debug(cmd)
        run(
            cmd, log=log, errmsg='Unable to sign image: %s',
            errvals=[self.image_file]
        )
        self.signed = datetime.utcnow().isoformat()
        # TODO?: self.signed_by? self.signed_fingerprint?
        self.storage.store(self.image_file + '.asc')

    def release_image(self):
        log = self._log
        if 'release_cmd' not in self.__dict__:
            log.warning("No 'release_cmd' set, not releasing image.")
            return

        base=self.image_name
        cmd = self.release_cmd.format(
                **self.__dict__, v_version=self.v_version,
                base=base
            ).split(' ')
        log.info(f'releasing {base}...')
        run(
            cmd, log=log, errmsg='Unable to release image: %s',
            errvals=[self.image_name]
        )
        self.released = datetime.utcnow().isoformat()

    def save_metadata(self, action):
        os.makedirs(self.local_dir, exist_ok=True)
        self._log.info('Saving image metadata')
        metadata = dict(self.tags)
        self.metadata_updated = datetime.utcnow().isoformat()
        metadata |= {
            'artifacts': self._get('artifacts', None),
            'metadata_updated': self.metadata_updated
        }
        metadata_path = self.local_dir / self.metadata_file
        self._yaml.dump(metadata, metadata_path)
        if action != 'local' and self.storage:
            self.storage.store(self.metadata_file, checksum=True)

    def load_metadata(self, step):
        new = True
        if step != 'final':
            # what's the latest uploaded revision?
            revision_glob = self.name.format(**(self.__dict__ | {'revision': '*'}))
            try:
                revision_yamls = self.storage.list(revision_glob + '.yaml', err_ok=True)
                new = not revision_yamls    # empty list is still new

            except RuntimeError:
                pass

            latest_revision = 0
            if not new:
                for y in revision_yamls:
                    yr = int(y.rstrip('.yaml').rsplit('r', 1)[1])
                    if yr > latest_revision:
                        latest_revision = yr

            self.revision = latest_revision

        metadata_path = self.local_dir / self.metadata_file
        if step != 'final' and not new and not metadata_path.exists():
            try:
                self.storage.retrieve(self.metadata_file)
            except RuntimeError as e:
                # TODO: don't we already log an error/warning?
                self._log.warning(f'Unable to retrieve from storage: {metadata_path}')

        self.load_local_metadata()  # if it exists
