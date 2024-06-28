from .interfaces.adapter import CloudAdapterInterface

# NOTE: Generic images are never imported or published because there's
#   no actual cloud provider associated with them.

class GenericAdapter(CloudAdapterInterface):

    def get_latest_imported_tags(self, project, image_key):
        return None

    def import_image(self, ic):
        pass

    def delete_image(self, config, image_id):
        pass

    def publish_image(self, ic):
        pass

def register(cloud, cred_provider=None):
    return GenericAdapter(cloud, cred_provider)
