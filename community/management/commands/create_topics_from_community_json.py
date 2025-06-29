from django.core.management.base import BaseCommand
from community.models import Community, Topic

class Command(BaseCommand):
    help = 'Create Topic model instances for each topic in Community.topics JSON field.'

    def handle(self, *args, **options):
        created_count = 0
        for community in Community.objects.all():
            for topic_name in community.topics:
                topic_name = topic_name.strip()
                if not topic_name:
                    continue
                topic_obj, created = Topic.objects.get_or_create(
                    name=topic_name,
                    community=community,
                    defaults={
                        'color': 'bg-gray-600',
                    }
                )
                if created:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f"Created topic '{topic_name}' for community '{community.name}'"))
        if created_count == 0:
            self.stdout.write(self.style.WARNING('No new topics were created.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Total topics created: {created_count}')) 