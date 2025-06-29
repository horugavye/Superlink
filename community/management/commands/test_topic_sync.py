from django.core.management.base import BaseCommand
from community.models import Community, Topic

class Command(BaseCommand):
    help = 'Test the topic sync functionality by updating a community\'s topics.'

    def handle(self, *args, **options):
        # Get the first community
        try:
            community = Community.objects.first()
            if not community:
                self.stdout.write(self.style.ERROR('No communities found.'))
                return
            
            self.stdout.write(f'Testing with community: {community.name}')
            self.stdout.write(f'Current topics: {community.topics}')
            
            # Count current Topic instances for this community
            current_topic_count = Topic.objects.filter(community=community).count()
            self.stdout.write(f'Current Topic instances: {current_topic_count}')
            
            # Add a new topic to the community
            new_topics = community.topics + ['New Test Topic']
            community.topics = new_topics
            community.save()
            
            # Check if new Topic instance was created
            new_topic_count = Topic.objects.filter(community=community).count()
            self.stdout.write(f'New Topic instances: {new_topic_count}')
            
            if new_topic_count > current_topic_count:
                self.stdout.write(self.style.SUCCESS('✅ Topic sync is working! New Topic instance was created.'))
            else:
                self.stdout.write(self.style.WARNING('⚠️ Topic sync may not be working as expected.'))
            
            # Show all topics for this community
            topics = Topic.objects.filter(community=community)
            self.stdout.write('All Topic instances for this community:')
            for topic in topics:
                self.stdout.write(f'  - {topic.name}')
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}')) 