from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import post_save
from django.dispatch import receiver

class User(AbstractUser):
    DEFAULT_AVATAR = 'avatars/default.jpg'
    
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, default=DEFAULT_AVATAR)
    cover_photo = models.ImageField(upload_to='covers/', null=True, blank=True)
    personal_story = models.TextField(blank=True)
    location = models.CharField(max_length=255, blank=True)
    website = models.URLField(blank=True)
    phone_number = models.CharField(max_length=50, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=50, blank=True)
    rating = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(5.0)],
        default=0.0
    )
    reputation_points = models.IntegerField(default=0)
    connection_strength = models.IntegerField(default=0)
    is_verified = models.BooleanField(default=False)
    is_mentor = models.BooleanField(default=False)
    account_type = models.CharField(
        max_length=50,
        choices=[
            ('personal', 'Personal'),
            ('professional', 'Professional'),
            ('business', 'Business'),
        ],
        default='personal'
    )
    profile_visibility = models.CharField(
        max_length=50,
        choices=[
            ('public', 'Public'),
            ('private', 'Private'),
            ('connections', 'Connections Only'),
        ],
        default='public'
    )
    two_factor_enabled = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    last_active = models.DateTimeField(null=True, blank=True)
    online_status = models.CharField(
        max_length=50,
        choices=[
            ('online', 'Online'),
            ('away', 'Away'),
            ('offline', 'Offline'),
            ('busy', 'Busy'),
        ],
        default='offline'
    )

    language_preference = models.CharField(max_length=10, default='en')
    theme_preference = models.CharField(
        max_length=50,
        choices=[
            ('light', 'Light'),
            ('dark', 'Dark'),
            ('system', 'System'),
        ],
        default='system'
    )
    timezone = models.CharField(max_length=50, default='UTC')
    post_count = models.IntegerField(default=0)
    follower_count = models.IntegerField(default=0)
    following_count = models.IntegerField(default=0)
    contribution_points = models.IntegerField(default=0)
    profile_completion = models.IntegerField(default=0)
    endorsement_count = models.IntegerField(default=0)

    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        indexes = [
            models.Index(fields=['username']),
            models.Index(fields=['email']),
            models.Index(fields=['rating']),
            models.Index(fields=['reputation_points']),
        ]

    def __str__(self):
        return self.username

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

    def update_profile_completion(self):
        fields = [
            self.avatar, self.bio, self.location, self.website,
            self.personal_story, self.phone_number, self.date_of_birth
        ]
        completed = sum(1 for field in fields if field)
        self.profile_completion = int((completed / len(fields)) * 100)
        self.save(update_fields=['profile_completion'])

    @property
    def role(self):
        try:
            # Get the most recent work experience role
            latest_work = self.work_experience.order_by('-start_date').first()
            return latest_work.role if latest_work else 'AI Professional'
        except Exception:
            return 'AI Professional'

    @property
    def badges(self):
        try:
            return [
                {
                    'name': badge.name,
                    'icon': badge.icon,
                    'color': f'text-{badge.category}-500'
                }
                for badge in self.badges.all()
            ]
        except Exception:
            return []

class UserSocialProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='social_profile')
    linkedin_url = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    medium_url = models.URLField(blank=True)
    portfolio_url = models.URLField(blank=True)
    blog_url = models.URLField(blank=True)

    def __str__(self):
        return f"{self.user.username}'s social profile"

    class Meta:
        db_table = 'user_social_profiles'

class UserAnalytics(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='analytics')
    profile_views = models.IntegerField(default=0)
    search_appearances = models.IntegerField(default=0)
    engagement_rate = models.FloatField(default=0.0)
    avg_response_time = models.DurationField(null=True)
    last_profile_update = models.DateTimeField(auto_now=True)
    activity_score = models.IntegerField(default=0)
    metrics = models.JSONField(default=dict)  # Stores detailed analytics data

    class Meta:
        db_table = 'user_analytics'

class UserBadge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='badges')
    name = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.CharField(max_length=50)
    awarded_date = models.DateTimeField(auto_now_add=True)
    category = models.CharField(max_length=50)
    level = models.IntegerField(default=1)

    class Meta:
        db_table = 'user_badges'

class UserCertification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='certifications')
    name = models.CharField(max_length=255)
    issuing_organization = models.CharField(max_length=255)
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    credential_id = models.CharField(max_length=255, blank=True)
    credential_url = models.URLField(blank=True)
    is_verified = models.BooleanField(default=False)

    class Meta:
        db_table = 'user_certifications'

class UserProject(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='projects')
    title = models.CharField(max_length=255)
    description = models.TextField()
    url = models.URLField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_ongoing = models.BooleanField(default=False)
    technologies = models.JSONField(default=list)
    team_size = models.IntegerField(default=1)
    role = models.CharField(max_length=255)
    achievements = models.TextField(blank=True)
    visibility = models.CharField(
        max_length=50,
        choices=[
            ('public', 'Public'),
            ('private', 'Private'),
            ('connections', 'Connections Only'),
        ],
        default='public'
    )

    class Meta:
        db_table = 'user_projects'

class Skill(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='skills')
    name = models.CharField(max_length=100)
    level = models.IntegerField(
        validators=[
            MinValueValidator(0),
            MaxValueValidator(100)
        ]
    )

    def get_level_display(self):
        if self.level >= 90:
            return 'Master'
        if self.level >= 70:
            return 'Expert'
        if self.level >= 50:
            return 'Advanced'
        if self.level >= 30:
            return 'Intermediate'
        return 'Beginner'

    def __str__(self):
        return f"{self.name} ({self.get_level_display()})"

    class Meta:
        db_table = 'skills'

class UserEndorsement(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_endorsements')
    endorser = models.ForeignKey(User, on_delete=models.CASCADE, related_name='given_endorsements')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_endorsements'
        unique_together = ('user', 'endorser', 'skill')

class UserBlock(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_users')
    blocked_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_by')
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_blocks'
        unique_together = ('user', 'blocked_user')

class PersonalityTag(models.Model):
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=20)
    users = models.ManyToManyField(User, related_name='personality_tags')

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'personality_tags'

class Language(models.Model):
    PROFICIENCY_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('native', 'Native'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='languages')
    name = models.CharField(max_length=50)
    proficiency = models.CharField(max_length=20, choices=PROFICIENCY_CHOICES)

    def __str__(self):
        return f"{self.name} ({self.proficiency})"

    class Meta:
        db_table = 'languages'

class UserAvailability(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='availability')
    mentoring = models.BooleanField(default=False)
    collaboration = models.BooleanField(default=False)
    networking = models.BooleanField(default=False)

    def __str__(self):
        return f"Availability for {self.user.username}"

    class Meta:
        db_table = 'user_availability'

class Education(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='education')
    school = models.CharField(max_length=255)
    degree = models.CharField(max_length=255)
    field = models.CharField(max_length=255)
    year = models.CharField(max_length=4)
    institution_type = models.CharField(
        max_length=50,
        choices=[
            ('university', 'University'),
            ('college', 'College'),
            ('high_school', 'High School'),
            ('bootcamp', 'Bootcamp'),
            ('online_course', 'Online Course'),
            ('other', 'Other')
        ],
        default='university'
    )
    duration = models.CharField(max_length=50, blank=True, help_text="e.g., 4 years, 2 years")
    gpa = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="GPA on a 4.0 scale"
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    achievements = models.JSONField(default=list, blank=True)
    skills_learned = models.JSONField(default=list, blank=True)
    location = models.CharField(max_length=255, blank=True)
    website = models.URLField(blank=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.degree} in {self.field} from {self.school}"

    class Meta:
        db_table = 'education'
        ordering = ['-end_date', '-start_date']

class WorkExperience(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='work_experience')
    company = models.CharField(max_length=255)
    role = models.CharField(max_length=255)
    duration = models.CharField(max_length=100)
    highlights = models.JSONField(default=list)
    employment_type = models.CharField(
        max_length=50,
        choices=[
            ('full-time', 'Full-time'),
            ('part-time', 'Part-time'),
            ('contract', 'Contract'),
            ('internship', 'Internship'),
            ('freelance', 'Freelance')
        ],
        default='full-time'
    )
    skills = models.JSONField(default=list)
    team_size = models.IntegerField(null=True, blank=True)
    projects_count = models.IntegerField(null=True, blank=True)
    impact_score = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        null=True,
        blank=True
    )
    endorsements = models.JSONField(default=list) 
    endorsement_count = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.role} at {self.company}"

    class Meta:
        db_table = 'work_experience'

class Achievement(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='achievements')
    title = models.CharField(max_length=255)
    date = models.DateField()
    description = models.TextField()
    category = models.CharField(max_length=50, default='award')
    impact = models.CharField(max_length=255, blank=True, null=True)
    team = models.CharField(max_length=255, blank=True, null=True)
    link = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.title

    class Meta:
        db_table = 'achievements'

class UserInterest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='interests')
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'user_interests'

class UserFollowing(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='following')
    following_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='followers')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} follows {self.following_user.username}"

    class Meta:
        db_table = 'user_following'
        unique_together = ('user', 'following_user')
