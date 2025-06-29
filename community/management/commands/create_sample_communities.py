from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from community.models import Community, CommunityMember
from django.utils.text import slugify
import random

User = get_user_model()

class Command(BaseCommand):
    help = 'Creates 5 sample communities with realistic data and members'

    def handle(self, *args, **kwargs):
        # Get or create a superuser for community creation
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@example.com',
                'is_staff': True,
                'is_superuser': True
            }
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
            self.stdout.write(self.style.SUCCESS('Created admin user'))

        # Create sample users
        sample_users = []
        for i in range(1, 21):  # Create 20 sample users
            user, created = User.objects.get_or_create(
                username=f'user{i}',
                defaults={
                    'email': f'user{i}@example.com',
                    'is_active': True
                }
            )
            if created:
                user.set_password('password123')
                user.save()
                sample_users.append(user)
                self.stdout.write(self.style.SUCCESS(f'Created user user{i}'))

        # Sample community data
        communities_data = [
            {
                'name': 'Tech Enthusiasts',
                'description': 'A community for technology lovers to discuss the latest innovations, gadgets, and tech trends. Share your knowledge and learn from others!',
                'category': 'tech',
                'topics': ['Programming', 'AI', 'Hardware', 'Software', 'Web Development'],
                'rules': [
                    'Be respectful to all members',
                    'No spam or self-promotion',
                    'Keep discussions tech-related',
                    'Share knowledge and help others'
                ],
                'is_private': False
            },
            {
                'name': 'Art & Creativity',
                'description': 'A space for artists, designers, and creative minds to share their work, get feedback, and collaborate on projects. All art forms welcome!',
                'category': 'art',
                'topics': ['Digital Art', 'Traditional Art', 'Design', 'Photography', 'Animation'],
                'rules': [
                    'Credit original artists',
                    'Constructive criticism only',
                    'No NSFW content',
                    'Share your creative process'
                ],
                'is_private': False
            },
            {
                'name': 'Gaming Legends',
                'description': 'Join fellow gamers to discuss strategies, share gaming experiences, and find teammates for your favorite games. From casual to competitive!',
                'category': 'gaming',
                'topics': ['PC Gaming', 'Console Gaming', 'Mobile Games', 'Esports', 'Game Development'],
                'rules': [
                    'No toxic behavior',
                    'Respect different gaming preferences',
                    'No cheating discussions',
                    'Keep it fun and friendly'
                ],
                'is_private': False
            },
            {
                'name': 'Science Explorers',
                'description': 'A community dedicated to scientific discussions, discoveries, and learning. Share research, ask questions, and explore the wonders of science!',
                'category': 'science',
                'topics': ['Physics', 'Biology', 'Chemistry', 'Astronomy', 'Mathematics'],
                'rules': [
                    'Back claims with sources',
                    'No pseudoscience',
                    'Respect scientific method',
                    'Encourage critical thinking'
                ],
                'is_private': False
            },
            {
                'name': 'Music Makers',
                'description': 'Connect with musicians, producers, and music enthusiasts. Share your music, collaborate on projects, and discuss all things music!',
                'category': 'music',
                'topics': ['Production', 'Instruments', 'Genres', 'Collaboration', 'Music Theory'],
                'rules': [
                    'Share your music journey',
                    'No copyright infringement',
                    'Be supportive of all skill levels',
                    'Respect different music tastes'
                ],
                'is_private': False
            }
        ]

        # Create communities and add members
        for data in communities_data:
            community, created = Community.objects.get_or_create(
                name=data['name'],
                defaults={
                    'slug': slugify(data['name']),
                    'description': data['description'],
                    'category': data['category'],
                    'topics': data['topics'],
                    'rules': data['rules'],
                    'is_private': data['is_private'],
                    'created_by': admin_user
                }
            )
            
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully created community "{data["name"]}"')
                )
                
                # Add members to the community
                # 1. Add admin (creator)
                CommunityMember.objects.create(
                    community=community,
                    user=admin_user,
                    role='admin'
                )
                
                # 2. Add 2 moderators
                for i in range(2):
                    CommunityMember.objects.create(
                        community=community,
                        user=sample_users[i],
                        role='moderator'
                    )
                
                # 3. Add 5-10 regular members
                num_members = random.randint(5, 10)
                for i in range(2, 2 + num_members):
                    if i < len(sample_users):
                        CommunityMember.objects.create(
                            community=community,
                            user=sample_users[i],
                            role='member'
                        )
                
                # Update members count
                community.members_count = CommunityMember.objects.filter(community=community).count()
                community.save()
                
                self.stdout.write(
                    self.style.SUCCESS(f'Added {community.members_count} members to "{data["name"]}"')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Community "{data["name"]}" already exists')
                )

        self.stdout.write(self.style.SUCCESS('Finished creating sample communities and members')) 