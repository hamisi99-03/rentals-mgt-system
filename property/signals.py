from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from property.models import Lease
from property.services import sync_unit_status


@receiver(post_save, sender=Lease)
def _sync_unit_on_lease_save(sender, instance, **kwargs):  # noqa: ANN001
    sync_unit_status(instance.unit)


@receiver(post_delete, sender=Lease)
def _sync_unit_on_lease_delete(sender, instance, **kwargs):  # noqa: ANN001
    sync_unit_status(instance.unit)
