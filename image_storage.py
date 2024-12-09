# vim: ts=4 et:

import copy
import hashlib
import shutil
import os

from glob import glob
from pathlib import Path
from subprocess import Popen, PIPE
from urllib.parse import urlparse

from image_tags import DictObj


def run(cmd, log, errmsg=None, errvals=[], err_ok=False, shell=False):
    # ensure command and error values are lists of strings
    errvals = [str(ev) for ev in errvals]
    if not shell:
        cmd = [str(c) for c in cmd]
    else:
        cmd = str(cmd)

    log.debug('COMMAND: %s', cmd)
    p = Popen(cmd, stdout=PIPE, stdin=PIPE, stderr=PIPE, encoding='utf8', shell=shell)
    out, err = p.communicate()
    if p.returncode:
        if errmsg:
            if err_ok:
                log.debug(errmsg, *errvals)

            else:
                log.error(errmsg, *errvals)

        log.debug('EXIT: %d / COMMAND: %s', p.returncode, cmd)
        log.debug('STDOUT:\n%s', out)
        log.debug('STDERR:\n%s', err)
        raise RuntimeError

    return out, err


class ImageStorage():

    def __init__(self, local, storage_url, log):
        self.log = log
        self.local = local
        self.url = storage_url.removesuffix('/')
        url = urlparse(self.url)
        if url.scheme not in ['', 'file', 'ssh']:
            self.log.error('Storage with "%s" scheme is unsupported', url.scheme)
            raise RuntimeError

        if url.scheme in ['', 'file']:
            self.scheme = 'file'
            self.remote = Path(url.netloc + url.path).expanduser()

        else:
            self.scheme = 'ssh'
            self.host = url.hostname
            self.remote = Path(url.path[1:])   # drop leading / -- use // for absolute path
            self.ssh = DictObj({
                'port': ['-p', url.port] if url.port else [],
                'user': ['-l', url.username] if url.username else [],
            })
            self.scp = DictObj({
                'port': ['-P', url.port] if url.port else [],
                'user': url.username + '@' if url.username else '',
            })

    def _checksum(self, file, save=False):
        log = self.log
        src = self.local
        log.debug("Calculating checksum for '%s'", file)
        sha512_hash = hashlib.sha512()
        with open(src / file, 'rb') as f:
            for block in iter(lambda: f.read(4096), b''):
                sha512_hash.update(block)

        checksum = sha512_hash.hexdigest()
        if save:
            log.debug("Saving '%s'", file + '.sha512')
            with open(str(src / file) + '.sha512', 'w') as f:
                print(checksum, file=f)

        return checksum

    def store(self, *files, checksum=False):
        log = self.log
        src = self.local
        dest = self.remote

        # take care of any globbing in file list
        files = [Path(p).name for p in sum([glob(str(src / f)) for f in files], [])]

        if not files:
            log.debug('No files to store')
            return

        if checksum:
            log.info('Creating checksum(s) for %s', files)
            for f in copy.copy(files):
                self._checksum(f, save=True)
                files.append(f + '.sha512')

        log.info('Storing %s', files)
        if self.scheme == 'file':
            dest.mkdir(parents=True, exist_ok=True)
            for file in files:
                shutil.copy2(src / file, dest / file)

            return

        url = self.url
        host = self.host
        ssh = self.ssh
        scp = self.scp
        run(
            ['ssh'] + ssh.port + ssh.user + [host, 'mkdir', '-p', dest],
            log=log, errmsg='Unable to ensure existence of %s', errvals=[url]
        )
        src_files = []
        for file in files:
            log.info('Storing %s', url + '/' + file)
            src_files.append(src / file)

        run(
            ['scp'] + scp.port + src_files + [scp.user + ':'.join([host, str(dest)])],
            log=log, errmsg='Failed to store files'
        )

    def retrieve(self, *files, checksum=False):
        log = self.log
        # TODO? use list()
        if not files:
            log.debug('No files to retrieve')
            return

        src = self.remote
        dest = self.local
        dest.mkdir(parents=True, exist_ok=True)
        if self.scheme == 'file':
            for file in files:
                log.debug('Retrieving %s', src / file)
                shutil.copy2(src / file, dest / file)

            return

        url = self.url
        host = self.host
        scp = self.scp
        src_files = []
        for file in files:
            log.debug('Retrieving %s', url + '/' + file)
            src_files.append(scp.user + ':'.join([host, str(src / file)]))

        run(
            ['scp'] + scp.port + src_files + [dest],
            log=log, errmsg='Failed to retrieve files'
        )

    # TODO: optional files=[]?
    def list(self, match=None, err_ok=False):
        log = self.log
        path = self.remote
        if not match:
            match = '*'

        files = []
        if self.scheme == 'file':
            path.mkdir(parents=True, exist_ok=True)
            log.debug('Listing of %s files in %s', match, path)
            files = sorted(glob(str(path / match)), key=os.path.getmtime, reverse=True)

        else:
            url = self.url
            host = self.host
            ssh = self.ssh
            log.debug('Listing %s files at %s', match, url)
            run(
                ['ssh'] + ssh.port + ssh.user + [host, 'mkdir', '-p', path],
                log=log, errmsg='Unable to create path', err_ok=err_ok
            )
            out, _ = run(
                ['ssh'] + ssh.port + ssh.user + [host, 'ls', '-1drt', path / match],
                log=log, errmsg='Failed to list files', err_ok=err_ok
            )
            files = out.splitlines()

        return [os.path.basename(f) for f in files]

    def remove(self, *files):
        log = self.log
        # TODO? use list()
        if not files:
            log.debug('No files to remove')
            return

        dest = self.remote
        if self.scheme == 'file':
            for file in files:
                path = dest / file
                log.debug('Removing %s', path)
                if path.exists():
                    path.unlink()

            return

        url = self.url
        host = self.host
        ssh = self.ssh
        dest_files = []
        for file in files:
            log.debug('Removing %s', url + '/' + file)
            dest_files.append(dest / file)

        run(
            ['ssh'] + ssh.port + ssh.user + [host, 'rm', '-f'] + dest_files,
            log=log, errmsg='Failed to remove files'
        )
