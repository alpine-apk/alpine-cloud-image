from .interfaces.adapter import CloudAdapterInterface

# NOTE: This stub allows images to be built locally and uploaded to storage,
#   but code for automated importing and publishing of images for this cloud
#   publisher has not yet been written.

class GCPCloudAdapter(CloudAdapterInterface):

    def import_image(self, ic):
        pass

    def delete_image(self, config, image_id):
        pass

    def publish_image(self, ic):
        pass

def register(cloud, cred_provider=None):
    return GCPCloudAdapter(cloud, cred_provider)
