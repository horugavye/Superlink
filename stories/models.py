from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import uuid
from datetime import timedelta

User = get_user_model()


class Story(models.Model):
    """Main Story model supporting all story types and features"""
    
    STORY_TYPES = [
        ('image', 'Image Story'),
        ('video', 'Video Story'),
        ('audio', 'Audio Story'),
        ('text', 'Text Story'),
        ('poll', 'Poll Story'),
        ('location', 'Location Story'),
        ('timecapsule', 'Time Capsule'),
        ('collaborative', 'Collaborative Story'),
        ('ai-remix', 'AI Remix'),
        ('story-thread', 'Story Thread'),
    ]
    
    THEME_CHOICES = [
        ('personal', 'Personal'),
        ('travel', 'Travel'),
        ('food', 'Food & Dining'),
        ('art', 'Art & Creativity'),
        ('wellness', 'Wellness'),
        ('social', 'Social'),
    ]
    
    # Basic fields
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stories')
    type = models.CharField(max_length=20, choices=STORY_TYPES, default='image')
    content = models.TextField()
    theme = models.CharField(max_length=20, choices=THEME_CHOICES, default='personal')
    
    # Media and presentation
    media_url = models.URLField(blank=True, null=True)
    media_file = models.FileField(upload_to='stories/media/', blank=True, null=True)
    duration = models.IntegerField(default=15, validators=[MinValueValidator(5), MaxValueValidator(300)])
    
    # Location data
    location_name = models.CharField(max_length=255, blank=True, null=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    
    # Time capsule functionality
    unlock_date = models.DateTimeField(blank=True, null=True)
    is_unlocked = models.BooleanField(default=True)
    
    # Story thread functionality
    parent_story = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True, related_name='child_stories')
    thread_id = models.UUIDField(blank=True, null=True)
    thread_title = models.CharField(max_length=255, blank=True, null=True)
    thread_order = models.IntegerField(default=0)
    
    # AI Remix data
    original_story = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True, related_name='remixes')
    ai_style = models.CharField(max_length=100, blank=True, null=True)
    ai_filters = models.JSONField(default=list, blank=True)
    
    # Metadata
    tags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    # Privacy and visibility
    is_public = models.BooleanField(default=True)
    allow_sharing = models.BooleanField(default=True)
    
    # Statistics
    views_count = models.IntegerField(default=0)
    shares_count = models.IntegerField(default=0)
    
    # Rating system
    rating = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(5.0)])
    total_ratings = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'stories'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['author', 'created_at']),
            models.Index(fields=['type', 'theme']),
            models.Index(fields=['thread_id', 'thread_order']),
            models.Index(fields=['unlock_date']),
            models.Index(fields=['is_active', 'is_public']),
        ]
    
    def __str__(self):
        return f"{self.author.username} - {self.content[:50]}"
    
    def save(self, *args, **kwargs):
        if not self.expires_at:
            # If the story is new and expires_at is not set, set it to 24 hours after creation
            if not self.pk:  # Only for new stories
                self.expires_at = timezone.now() + timedelta(hours=24)
        super().save(*args, **kwargs)
    
    def is_expired(self):
        """Check if story has expired"""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    def can_be_viewed_by(self, user):
        """Check if user can view this story"""
        if not self.is_active:
            return False
        
        if self.is_expired():
            return False
        
        if self.unlock_date and timezone.now() < self.unlock_date:
            return False
        
        if self.is_public:
            return True
        
        # Add more privacy logic here if needed
        return True
    
    def update_stats(self):
        """Update story statistics"""
        self.shares_count = self.shares.count()
        self.save(update_fields=['shares_count'])


class StoryCollaborator(models.Model):
    """Model for collaborative stories"""
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name='collaborators')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='collaborated_stories')
    role = models.CharField(max_length=50, default='contributor')  # contributor, editor, viewer
    joined_at = models.DateTimeField(auto_now_add=True)
    can_edit = models.BooleanField(default=True)
    can_delete = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'story_collaborators'
        unique_together = ('story', 'user')
    
    def __str__(self):
        return f"{self.user.username} - {self.story.content[:30]}"


class StoryInteractive(models.Model):
    """Model for interactive story elements like polls"""
    INTERACTIVE_TYPES = [
        ('poll', 'Poll'),
        ('quiz', 'Quiz'),
        ('game', 'Game'),
    ]
    
    story = models.OneToOneField(Story, on_delete=models.CASCADE, related_name='interactive')
    type = models.CharField(max_length=20, choices=INTERACTIVE_TYPES, default='poll')
    options = models.JSONField(default=list)  # For polls: list of options
    correct_answer = models.IntegerField(blank=True, null=True)  # For quizzes
    settings = models.JSONField(default=dict)  # Additional settings
    
    class Meta:
        db_table = 'story_interactives'
    
    def __str__(self):
        return f"{self.story.content[:30]} - {self.type}"


class StoryInteraction(models.Model):
    """Model for user interactions with stories"""
    INTERACTION_TYPES = [
        ('like', 'Like'),
        ('comment', 'Comment'),
        ('share', 'Share'),
        ('view', 'View'),
        ('rate', 'Rate'),
        ('poll_vote', 'Poll Vote'),
    ]
    
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name='interactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='story_interactions')
    interaction_type = models.CharField(max_length=20, choices=INTERACTION_TYPES)
    value = models.JSONField(default=dict)  # For ratings, poll votes, etc.
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'story_interactions'
        unique_together = ('story', 'user', 'interaction_type')
        indexes = [
            models.Index(fields=['story', 'interaction_type']),
            models.Index(fields=['user', 'interaction_type']),
        ]
    
    def __str__(self):
        return f"{self.user.username} {self.interaction_type} on {self.story.content[:30]}"


class StoryShare(models.Model):
    """Model for story shares"""
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name='shares')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='story_shares')
    platform = models.CharField(max_length=50, blank=True)  # facebook, twitter, etc.
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'story_shares'
    
    def __str__(self):
        return f"{self.user.username} shared {self.story.content[:30]}"


class StoryRating(models.Model):
    """Model for story ratings"""
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name='ratings')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='story_ratings')
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'story_ratings'
        unique_together = ('story', 'user')
    
    def __str__(self):
        return f"{self.user.username} rated {self.story.content[:30]} with {self.rating} stars"


class StoryView(models.Model):
    """Model for story views"""
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name='views')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='story_views')
    viewed_at = models.DateTimeField(auto_now_add=True)
    view_duration = models.IntegerField(default=0)  # seconds
    completed = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'story_views'
        unique_together = ('story', 'user')
    
    def __str__(self):
        return f"{self.user.username} viewed {self.story.content[:30]}"


class StoryTag(models.Model):
    """Model for story tags"""
    name = models.CharField(max_length=100, unique=True)
    color = models.CharField(max_length=20, default='#6366f1')
    usage_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'story_tags'
        ordering = ['-usage_count']
    
    def __str__(self):
        return self.name


class StoryBookmark(models.Model):
    """Model for story bookmarks"""
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name='bookmarks')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='story_bookmarks')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'story_bookmarks'
        unique_together = ('story', 'user')
    
    def __str__(self):
        return f"{self.user.username} bookmarked {self.story.content[:30]}"


class StoryReport(models.Model):
    """Model for story reports"""
    REPORT_REASONS = [
        ('inappropriate', 'Inappropriate Content'),
        ('spam', 'Spam'),
        ('harassment', 'Harassment'),
        ('copyright', 'Copyright Violation'),
        ('other', 'Other'),
    ]
    
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name='reports')
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='story_reports')
    reason = models.CharField(max_length=20, choices=REPORT_REASONS)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'story_reports'
        unique_together = ('story', 'reporter')
    
    def __str__(self):
        return f"Report by {self.reporter.username} on {self.story.content[:30]}"


class StoryAnalytics(models.Model):
    """Model for story analytics"""
    story = models.OneToOneField(Story, on_delete=models.CASCADE, related_name='analytics')
    total_views = models.IntegerField(default=0)
    unique_views = models.IntegerField(default=0)
    avg_view_duration = models.FloatField(default=0.0)
    completion_rate = models.FloatField(default=0.0)
    engagement_rate = models.FloatField(default=0.0)
    shares_count = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'story_analytics'
    
    def __str__(self):
        return f"Analytics for {self.story.content[:30]}"
    
    def update_analytics(self):
        """Update analytics based on current data"""
        self.total_views = self.story.views.count()
        self.unique_views = self.story.views.values('user').distinct().count()
        self.shares_count = self.story.shares.count()
        
        # Calculate average view duration
        view_durations = self.story.views.values_list('view_duration', flat=True)
        if view_durations:
            self.avg_view_duration = sum(view_durations) / len(view_durations)
        
        # Calculate completion rate
        completed_views = self.story.views.filter(completed=True).count()
        if self.total_views > 0:
            self.completion_rate = (completed_views / self.total_views) * 100
        
        # Calculate engagement rate (no likes, so just shares)
        total_interactions = self.shares_count
        if self.unique_views > 0:
            self.engagement_rate = (total_interactions / self.unique_views) * 100
        
        self.save()
