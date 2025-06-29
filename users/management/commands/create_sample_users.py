from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Q
from datetime import datetime, timedelta
import random
from faker import Faker
from users.models import (
    UserSocialProfile, UserAnalytics, UserBadge, UserCertification,
    UserProject, Skill, UserEndorsement, PersonalityTag, Language,
    UserAvailability, Education, WorkExperience, Achievement,
    UserInterest, UserFollowing
)
from connections.models import Connection, ConnectionRequest, UserSuggestion

User = get_user_model()
fake = Faker()

class Command(BaseCommand):
    help = 'Creates 20 sample users with complete profiles and connections'

    def handle(self, *args, **kwargs):
        self.stdout.write('Creating sample users...')
        
        # Create personality tags
        personality_tags = [
            ('Creative', '#FF5733'),
            ('Analytical', '#33FF57'),
            ('Leader', '#3357FF'),
            ('Team Player', '#F333FF'),
            ('Innovator', '#33FFF3'),
            ('Problem Solver', '#FF33F3'),
            ('Communicator', '#F3FF33'),
            ('Organizer', '#33FF33'),
        ]
        
        tags = []
        for name, color in personality_tags:
            tag, _ = PersonalityTag.objects.get_or_create(name=name, color=color)
            tags.append(tag)

        # Create 20 users
        users = []
        for i in range(20):
            # Create base user
            user = User.objects.create_user(
                username=fake.user_name(),
                email=fake.email(),
                password='password123',
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                bio=fake.text(max_nb_chars=200),
                location=fake.city(),
                website=fake.url(),
                phone_number=fake.phone_number(),
                date_of_birth=fake.date_of_birth(minimum_age=18, maximum_age=65),
                gender=random.choice(['M', 'F', 'O']),
                rating=round(random.uniform(3.5, 5.0), 1),
                reputation_points=random.randint(100, 1000),
                is_verified=random.choice([True, False]),
                is_mentor=random.choice([True, False]),
                account_type=random.choice(['personal', 'professional', 'business']),
                profile_visibility=random.choice(['public', 'private', 'connections']),
                personal_story=fake.text(max_nb_chars=500),
                online_status=random.choice(['online', 'away', 'offline', 'busy']),
                profile_completion=random.randint(60, 100)
            )
            users.append(user)

            # Create social profile
            UserSocialProfile.objects.create(
                user=user,
                linkedin_url=fake.url(),
                github_url=fake.url(),
                twitter_url=fake.url(),
                facebook_url=fake.url(),
                instagram_url=fake.url()
            )

            # Create analytics
            UserAnalytics.objects.create(
                user=user,
                profile_views=random.randint(100, 1000),
                search_appearances=random.randint(50, 500),
                engagement_rate=round(random.uniform(0.1, 0.5), 2),
                activity_score=random.randint(50, 200)
            )

            # Add badges
            for _ in range(random.randint(1, 5)):
                UserBadge.objects.create(
                    user=user,
                    name=fake.word().capitalize(),
                    description=fake.text(max_nb_chars=100),
                    icon=fake.word(),
                    category=random.choice(['skill', 'achievement', 'contribution']),
                    level=random.randint(1, 5)
                )

            # Add certifications
            for _ in range(random.randint(1, 3)):
                UserCertification.objects.create(
                    user=user,
                    name=fake.word().capitalize() + ' Certification',
                    issuing_organization=fake.company(),
                    issue_date=fake.date_this_decade(),
                    expiry_date=fake.future_date(),
                    credential_id=fake.uuid4(),
                    is_verified=random.choice([True, False])
                )

            # Add projects
            for _ in range(random.randint(1, 4)):
                UserProject.objects.create(
                    user=user,
                    title=fake.catch_phrase(),
                    description=fake.text(max_nb_chars=200),
                    url=fake.url(),
                    start_date=fake.date_this_decade(),
                    end_date=fake.date_this_decade(),
                    is_ongoing=random.choice([True, False]),
                    technologies=random.sample(['Python', 'JavaScript', 'Java', 'C++', 'React', 'Django', 'Flask'], k=random.randint(2, 5)),
                    team_size=random.randint(1, 10),
                    role=random.choice(['Developer', 'Designer', 'Project Manager', 'Team Lead']),
                    achievements=fake.text(max_nb_chars=100)
                )

            # Add skills
            skills = []
            for skill_name in random.sample(['Python', 'JavaScript', 'Java', 'C++', 'React', 'Django', 'Flask', 'Node.js', 'SQL', 'MongoDB'], k=random.randint(3, 7)):
                skill = Skill.objects.create(
                    user=user,
                    name=skill_name,
                    level=random.randint(30, 100)
                )
                skills.append(skill)

            # Add languages
            for _ in range(random.randint(1, 3)):
                Language.objects.create(
                    user=user,
                    name=random.choice(['English', 'Spanish', 'French', 'German', 'Chinese', 'Japanese']),
                    proficiency=random.choice(['beginner', 'intermediate', 'advanced', 'native'])
                )

            # Add education
            for _ in range(random.randint(1, 3)):
                Education.objects.create(
                    user=user,
                    school=fake.company(),
                    degree=random.choice(['Bachelor', 'Master', 'PhD', 'Associate']),
                    field=random.choice(['Computer Science', 'Engineering', 'Business', 'Arts', 'Science']),
                    year=str(random.randint(2010, 2023)),
                    institution_type=random.choice(['university', 'college', 'high_school', 'bootcamp']),
                    gpa=round(random.uniform(2.0, 4.0), 2),
                    start_date=fake.date_this_decade(),
                    end_date=fake.date_this_decade(),
                    description=fake.text(max_nb_chars=200)
                )

            # Add work experience
            for _ in range(random.randint(1, 4)):
                WorkExperience.objects.create(
                    user=user,
                    company=fake.company(),
                    role=random.choice(['Software Engineer', 'Product Manager', 'Data Scientist', 'UX Designer', 'DevOps Engineer']),
                    duration=f"{random.randint(1, 5)} years",
                    highlights=[fake.text(max_nb_chars=100) for _ in range(3)],
                    employment_type=random.choice(['full-time', 'part-time', 'contract', 'internship']),
                    skills=random.sample(['Python', 'JavaScript', 'Java', 'C++', 'React', 'Django', 'Flask'], k=random.randint(2, 5)),
                    team_size=random.randint(5, 50),
                    projects_count=random.randint(1, 10),
                    impact_score=random.randint(50, 100)
                )

            # Add achievements
            for _ in range(random.randint(1, 3)):
                Achievement.objects.create(
                    user=user,
                    title=fake.catch_phrase(),
                    date=fake.date_this_decade(),
                    description=fake.text(max_nb_chars=200),
                    category=random.choice(['award', 'certification', 'project', 'publication']),
                    impact=fake.text(max_nb_chars=100)
                )

            # Add interests
            for _ in range(random.randint(3, 8)):
                UserInterest.objects.create(
                    user=user,
                    name=random.choice(['Programming', 'AI', 'Machine Learning', 'Web Development', 'Mobile Development', 'Cloud Computing', 'Cybersecurity', 'Data Science', 'UI/UX Design', 'DevOps'])
                )

            # Add personality tags
            user.personality_tags.add(*random.sample(tags, k=random.randint(2, 4)))

        # Create connections (max 5 per user)
        for user in users:
            # Get potential connections (excluding self and existing connections)
            potential_connections = [u for u in users if u != user and not Connection.objects.filter(
                Q(user1=user, user2=u) | Q(user1=u, user2=user)
            ).exists()]
            
            # Create up to 5 connections
            for other_user in random.sample(potential_connections, k=min(5, len(potential_connections))):
                Connection.objects.create(
                    user1=user,
                    user2=other_user,
                    connection_strength=random.randint(50, 100),
                    last_interaction=timezone.now() - timedelta(days=random.randint(0, 30))
                )

        self.stdout.write(self.style.SUCCESS('Successfully created 20 sample users with complete profiles and connections')) 