# vim: ts=4 et:

from . import aws, nocloud, azure, gcp, oci, generic

ADAPTERS = {}


def register(*mods):
    for mod in mods:
        cloud = mod.__name__.split('.')[-1]
        if p := mod.register(cloud):
            ADAPTERS[cloud] = p


register(
    aws,        # well-tested and fully supported
    nocloud,    # beta, supported, lacks import and publish
    azure,      # beta, supported, lacks import and publish
    gcp,        # beta, supported, lacks import and publish
    oci,        # beta, supported, lacks import and publish
    generic,    # alpha, needs testing, lacks import and publish
)


# using a credential provider is optional, set across all adapters
def set_credential_provider(debug=False):
    from .identity_broker_client import IdentityBrokerClient
    cred_provider = IdentityBrokerClient(debug=debug)
    for adapter in ADAPTERS.values():
        adapter.cred_provider = cred_provider


### forward to the correct adapter


def import_image(config):
    return ADAPTERS[config.cloud].import_image(config)


def delete_image(config, image_id):
    return ADAPTERS[config.cloud].delete_image(image_id)


def publish_image(config):
    return ADAPTERS[config.cloud].publish_image(config)

# supported actions
def actions(config):
    return ADAPTERS[config.cloud].ACTIONS
