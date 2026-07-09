from celery import shared_task

from apps.emailcenter.services import send_campaign


@shared_task
def send_campaign_task(campaign_id):
    """Deliver an admin email campaign off the request thread."""
    send_campaign(campaign_id)
