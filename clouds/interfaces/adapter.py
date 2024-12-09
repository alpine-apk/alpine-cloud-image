# vim: ts=4 et:

class CloudAdapterInterface:

    ACTIONS = []

    def __init__(self, cloud, cred_provider=None):
        self._sdk = None
        self._sessions = {}
        self.cloud = cloud
        self.cred_provider = cred_provider
        self._default_region = None

    @property
    def sdk(self):
        raise NotImplementedError

    @property
    def regions(self):
        raise NotImplementedError

    @property
    def default_region(self):
        raise NotImplementedError

    def credentials(self, region=None):
        raise NotImplementedError

    def session(self, region=None):
        raise NotImplementedError

    def import_image(self, config):
        raise NotImplementedError

    def delete_image(self, config, image_id):
        raise NotImplementedError

    def publish_image(self, config):
        raise NotImplementedError
