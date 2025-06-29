from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.db.models import Avg, Q
import json
import decimal
from django.core.exceptions import ValidationError, ObjectDoesNotExist
import logging

logger = logging.getLogger(__name__)

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

class Community(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField()
    icon = models.ImageField(
        upload_to='community_icons/',
        help_text='Community profile image/icon (recommended size: 256x256px)',
        null=True,
        blank=True,
        default='community_icons/default_community_icon.png'
    )
    banner = models.ImageField(
        upload_to='community_banners/',
        help_text='Community cover photo (recommended size: 1200x400px)',
        null=True,
        blank=True,
        default='community_banners/default_community_banner.png'
    )
    category = models.CharField(max_length=50, choices=[
        ('tech', 'Technology'),
        ('science', 'Science'),
        ('art', 'Art'),
        ('gaming', 'Gaming'),
        ('music', 'Music'),
        ('sports', 'Sports'),
        ('education', 'Education'),
        ('other', 'Other')
    ])
    topics = models.JSONField(default=list)  # List of topic strings
    rules = models.JSONField(default=list)  # List of rule strings
    is_private = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_communities')
    members_count = models.PositiveIntegerField(default=0)
    online_count = models.PositiveIntegerField(default=0)
    activity_score = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(100)])  # 0-100 percentage

    class Meta:
        verbose_name_plural = "Communities"
        ordering = ['-members_count', '-activity_score']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        
        # Check if this is an update and if topics have changed
        topics_changed = False
        if self.pk:  # This is an update
            try:
                old_instance = Community.objects.get(pk=self.pk)
                topics_changed = old_instance.topics != self.topics
            except Community.DoesNotExist:
                topics_changed = True
        else:
            topics_changed = bool(self.topics)  # New community with topics
        
        # Save the community first to ensure it has an ID
        super().save(*args, **kwargs)
        
        # Sync topics if they've changed or this is a new community
        if topics_changed:
            self.sync_topics()
    
    def sync_topics(self):
        """Sync Topic model instances with the topics JSON field"""
        if not self.topics:
            # If no topics in JSON, remove all Topic instances for this community
            Topic.objects.filter(community=self).delete()
            return
        
        # Get current topic names from JSON
        current_topic_names = {topic.strip() for topic in self.topics if topic.strip()}
        
        # Get existing Topic instances for this community
        existing_topics = Topic.objects.filter(community=self)
        existing_topic_names = {topic.name for topic in existing_topics}
        
        # Create new topics that don't exist
        for topic_name in current_topic_names:
            if topic_name not in existing_topic_names:
                Topic.objects.create(
                    name=topic_name,
                    community=self,
                    color='bg-gray-600'
                )
        
        # Remove topics that are no longer in the JSON field
        topics_to_remove = existing_topic_names - current_topic_names
        if topics_to_remove:
            Topic.objects.filter(community=self, name__in=topics_to_remove).delete()

    def count_members(self):
        """Count all members in the community, including admins, moderators, and regular members."""
        count = self.members.count()
        print(f"[Backend] Community '{self.name}' member count: {count}")
        print(f"[Backend] Member details - Admins: {self.members.filter(role='admin').count()}, Moderators: {self.members.filter(role='moderator').count()}, Members: {self.members.filter(role='member').count()}")
        return count

    def update_members_count(self):
        """Update the members_count field with the current count of members."""
        old_count = self.members_count
        self.members_count = self.count_members()
        print(f"[Backend] Updated members_count field from {old_count} to: {self.members_count}")
        self.save(update_fields=['members_count'])

    def __str__(self):
        return self.name

class CommunityMember(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('moderator', 'Moderator'),
        ('member', 'Member')
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name='members')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)
    last_active = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    contributions = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ['user', 'community']
        indexes = [
            models.Index(fields=['user', 'last_active']),
            models.Index(fields=['community', 'role']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.community.name} ({self.role})"

@receiver([post_save, post_delete], sender=CommunityMember)
def update_community_member_count(sender, instance, **kwargs):
    """Update the member count of a community when members are added or removed."""
    print(f"[Backend] Signal triggered for community: {instance.community.name}")
    print(f"[Backend] Action: {'Created' if kwargs.get('created') else 'Updated' if kwargs.get('update_fields') else 'Deleted'}")
    print(f"[Backend] Member role: {instance.role}")
    instance.community.update_members_count()

class Topic(models.Model):
    name = models.CharField(max_length=50)
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name='topic_objects')
    color = models.CharField(max_length=20, default='bg-gray-600')  # Tailwind color class

    class Meta:
        unique_together = ['name', 'community']

    def __str__(self):
        return f"{self.name} - {self.community.name}"

class Post(models.Model):
    POST_VISIBILITY_CHOICES = [
        ('personal_private', 'Only Me'),
        ('personal_connections', 'My Connections'),
        ('personal_public', 'Everyone'),
        ('community', 'Community Only')
    ]

    community = models.ForeignKey(
        Community, 
        related_name='%(class)s_posts',  # This will be replaced with personal_posts or community_posts
        null=True, 
        blank=True, 
        on_delete=models.CASCADE
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    content = models.TextField()
    visibility = models.CharField(max_length=20, choices=POST_VISIBILITY_CHOICES, default='personal_private')
    is_pinned = models.BooleanField(default=False)
    is_edited = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    view_count = models.PositiveIntegerField(default=0)
    rating = models.DecimalField(
        max_digits=3, 
        decimal_places=2, 
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    total_ratings = models.PositiveIntegerField(default=0)
    comment_count = models.PositiveIntegerField(default=0)
    topics = models.ManyToManyField(
        Topic, 
        related_name='%(class)s_posts',  # This will be replaced with personal_posts or community_posts
        blank=True
    )

    class Meta:
        abstract = True
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            models.Index(fields=['visibility', 'created_at']),
        ]

    def clean(self):
        """Validate the post data before saving"""
        if self.visibility.startswith('personal_'):
            # For personal posts, ensure no community is set
            if self.community:
                raise ValidationError({
                    'community': 'Personal posts should not have a community.'
                })
        elif self.visibility == 'community':
            # For community posts, ensure a community is set
            if not self.community:
                raise ValidationError({
                    'community': 'Community posts must belong to a community.'
                })
            # Ensure the author is a member of the community
            if not CommunityMember.objects.filter(
                community=self.community,
                user=self.author,
                is_active=True
            ).exists():
                raise ValidationError({
                    'community': 'You must be a member of the community to post there.'
                })

    def save(self, *args, **kwargs):
        # Run validation
        self.clean()
        
        # For personal posts, ensure no community is set
        if self.visibility.startswith('personal_'):
            self.community = None

        # Handle edited status
        if self.pk:  # If post exists
            old_post = self.__class__.objects.get(pk=self.pk)
            if old_post.content != self.content:
                self.is_edited = True
                self.edited_at = timezone.now()

        super().save(*args, **kwargs)

    def __str__(self):
        if self.visibility.startswith('personal_'):
            return f"{self.title} - Personal Post ({self.get_visibility_display()})"
        return f"{self.title} - {self.community.name}"

class PersonalPost(Post):
    """Model for personal posts that are not associated with any community"""
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['author', 'visibility', 'created_at']),
        ]

    def clean(self):
        """Validate that personal posts don't have a community"""
        if self.community:
            raise ValidationError({
                'community': 'Personal posts should not have a community.'
            })
        super().clean()

    def save(self, *args, **kwargs):
        self.community = None  # Ensure no community is set
        super().save(*args, **kwargs)

class CommunityPost(Post):
    """Model for posts that are associated with a community"""
    class Meta:
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            models.Index(fields=['community', 'visibility', 'created_at']),
        ]

    def clean(self):
        """Validate that community posts have a community and the author is a member"""
        if not self.community:
            raise ValidationError({
                'community': 'Community posts must belong to a community.'
            })
        if not CommunityMember.objects.filter(
            community=self.community,
            user=self.author,
            is_active=True
        ).exists():
            raise ValidationError({
                'community': 'You must be a member of the community to post there.'
            })
        super().clean()

    def save(self, *args, **kwargs):
        if not self.visibility == 'community':
            self.visibility = 'community'  # Force community visibility
        super().save(*args, **kwargs)

class PostMedia(models.Model):
    MEDIA_TYPES = [
        ('image', 'Image'),
        ('video', 'Video')
    ]

    personal_post = models.ForeignKey(PersonalPost, on_delete=models.CASCADE, related_name='media', null=True, blank=True)
    community_post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name='media', null=True, blank=True)
    type = models.CharField(max_length=10, choices=MEDIA_TYPES)
    file = models.FileField(upload_to='post_media/')
    thumbnail = models.ImageField(upload_to='post_thumbnails/', null=True, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def clean(self):
        """Validate that exactly one post is set"""
        if bool(self.personal_post) == bool(self.community_post):
            raise ValidationError('Exactly one of personal_post or community_post must be set')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        post = self.personal_post or self.community_post
        return f"{self.type} for {post.title}"

class Comment(models.Model):
    personal_post = models.ForeignKey(PersonalPost, on_delete=models.CASCADE, related_name='comments', null=True, blank=True)
    community_post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name='comments', null=True, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_top_comment = models.BooleanField(default=False)
    rating = models.DecimalField(
        max_digits=3, 
        decimal_places=2, 
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    total_ratings = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def clean(self):
        """Validate that exactly one post is set, using IDs to avoid DoesNotExist errors"""
        personal_post_id = getattr(self, "personal_post_id", None)
        community_post_id = getattr(self, "community_post_id", None)
        if bool(personal_post_id) == bool(community_post_id):
            raise ValidationError('Exactly one of personal_post or community_post must be set')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        try:
            post = self.personal_post or self.community_post
            post_title = post.title if post else "Unknown"
        except (CommunityPost.DoesNotExist, PersonalPost.DoesNotExist, AttributeError):
            post_title = "Deleted Post"
        return f"Comment by {self.author.username} on {post_title}"

class Reply(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='replies')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    parent_reply = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='nested_replies')
    rating = models.DecimalField(
        max_digits=3, 
        decimal_places=2, 
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    total_ratings = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = "Replies"
        ordering = ['created_at']

    def __str__(self):
        return f"Reply by {self.author.username} on {self.comment}"

class PostRating(models.Model):
    personal_post = models.ForeignKey(PersonalPost, on_delete=models.CASCADE, related_name='ratings', null=True, blank=True)
    community_post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name='ratings', null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [
            ('personal_post', 'user'),
            ('community_post', 'user')
        ]

    def clean(self):
        """Validate that exactly one post is set"""
        if bool(self.personal_post) == bool(self.community_post):
            raise ValidationError('Exactly one of personal_post or community_post must be set')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        post = self.personal_post or self.community_post
        return f"Rating {self.rating} by {self.user.username} on {post.title}"

class CommentRating(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='ratings')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['comment', 'user']

    def __str__(self):
        return f"Rating {self.rating} by {self.user.username} on comment {self.comment.id}"

class ReplyRating(models.Model):
    reply = models.ForeignKey(Reply, on_delete=models.CASCADE, related_name='ratings')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['reply', 'user']

    def __str__(self):
        return f"Rating {self.rating} by {self.user.username} on reply {self.reply.id}"

@receiver(post_save, sender=PostRating)
def update_post_rating(sender, instance, created, **kwargs):
    post = instance.personal_post or instance.community_post
    if isinstance(post, PersonalPost):
        ratings = PostRating.objects.filter(personal_post=post)
    else:  # CommunityPost
        ratings = PostRating.objects.filter(community_post=post)
        
    post.total_ratings = ratings.count()
    post.rating = ratings.aggregate(Avg('rating'))['rating__avg'] or 0
    post.save()

    # Send WebSocket update if it's a community post
    if isinstance(post, CommunityPost):
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"community_{post.community.slug}",
            {
                'type': 'rating_update',
                'data': {
                    'post_id': post.id,
                    'rating': float(post.rating),
                    'total_ratings': post.total_ratings,
                    'user_rating': None  # This will be set by the frontend based on the current user
                }
            }
        )

@receiver(post_delete, sender=PostRating)
def update_post_rating_on_delete(sender, instance, **kwargs):
    """Update post rating and total ratings count when a rating is deleted"""
    try:
        post = instance.personal_post or instance.community_post
        if post:
            if isinstance(post, PersonalPost):
                ratings = PostRating.objects.filter(personal_post=post)
            else:  # CommunityPost
                ratings = PostRating.objects.filter(community_post=post)
            
            post.total_ratings = ratings.count()
            post.rating = ratings.aggregate(Avg('rating'))['rating__avg'] or 0
            post.save()

            # Send WebSocket update if it's a community post
            if isinstance(post, CommunityPost):
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"community_{post.community.slug}",
                    {
                        'type': 'rating_update',
                        'data': {
                            'post_id': post.id,
                            'rating': float(post.rating),
                            'total_ratings': post.total_ratings,
                            'user_rating': None  # This will be set by the frontend based on the current user
                        }
                    }
                )
    except (PersonalPost.DoesNotExist, CommunityPost.DoesNotExist, AttributeError):
        # Post has already been deleted or is inaccessible
        pass

@receiver(post_save, sender=CommentRating)
def update_comment_rating(sender, instance, created, **kwargs):
    comment = instance.comment
    ratings = CommentRating.objects.filter(comment=comment)
    comment.total_ratings = ratings.count()
    comment.rating = ratings.aggregate(Avg('rating'))['rating__avg'] or 0
    comment.save()

    # Send WebSocket update if the comment is in a community post
    post = comment.personal_post or comment.community_post
    if isinstance(post, CommunityPost):
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"community_{post.community.slug}",
            {
                'type': 'rating_update',
                'data': {
                    'post_id': post.id,
                    'comment_id': comment.id,
                    'rating': float(comment.rating),
                    'total_ratings': comment.total_ratings,
                    'user_rating': None  # This will be set by the frontend based on the current user
                }
            }
        )

@receiver(post_delete, sender=CommentRating)
def update_comment_rating_on_delete(sender, instance, **kwargs):
    comment = instance.comment
    ratings = CommentRating.objects.filter(comment=comment)
    comment.total_ratings = ratings.count()
    comment.rating = ratings.aggregate(Avg('rating'))['rating__avg'] or 0
    # Only save if the related post still exists
    personal_post_id = getattr(comment, "personal_post_id", None)
    community_post_id = getattr(comment, "community_post_id", None)
    post_exists = True
    if community_post_id:
        from community.models import CommunityPost
        try:
            CommunityPost.objects.get(pk=community_post_id)
        except CommunityPost.DoesNotExist:
            post_exists = False
    elif personal_post_id:
        from community.models import PersonalPost
        try:
            PersonalPost.objects.get(pk=personal_post_id)
        except PersonalPost.DoesNotExist:
            post_exists = False
    if post_exists:
        comment.save()
        # Send WebSocket update if the comment is in a community post
        post = comment.personal_post or comment.community_post
        if isinstance(post, CommunityPost):
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"community_{post.community.slug}",
                {
                    'type': 'rating_update',
                    'data': {
                        'post_id': post.id,
                        'comment_id': comment.id,
                        'rating': float(comment.rating),
                        'total_ratings': comment.total_ratings,
                        'user_rating': None
                    }
                }
            )

@receiver(post_save, sender=ReplyRating)
def update_reply_rating(sender, instance, created, **kwargs):
    reply = instance.reply
    ratings = ReplyRating.objects.filter(reply=reply)
    reply.total_ratings = ratings.count()
    reply.rating = ratings.aggregate(Avg('rating'))['rating__avg'] or 0
    reply.save()

    # Safely get the related post (personal or community)
    personal_post = getattr(reply.comment, 'personal_post', None)
    community_post = getattr(reply.comment, 'community_post', None)
    post = personal_post or community_post
    if not post:
        return  # No related post found, nothing to update

    # Send WebSocket update if the reply is in a community post
    if isinstance(post, CommunityPost):
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"community_{post.community.slug}",
            {
                'type': 'rating_update',
                'data': {
                    'post_id': post.id,
                    'comment_id': reply.comment.id,
                    'reply_id': reply.id,
                    'rating': float(reply.rating),
                    'total_ratings': reply.total_ratings,
                    'user_rating': None
                }
            }
        )

@receiver(post_delete, sender=ReplyRating)
def update_reply_rating_on_delete(sender, instance, **kwargs):
    try:
        reply = instance.reply
        ratings = ReplyRating.objects.filter(reply=reply)
        reply.total_ratings = ratings.count()
        reply.rating = ratings.aggregate(Avg('rating'))['rating__avg'] or 0
        reply.save()

        # Safely get the related post (personal or community)
        personal_post = getattr(reply.comment, 'personal_post', None)
        community_post = getattr(reply.comment, 'community_post', None)
        post = personal_post or community_post
        if not post:
            return  # No related post found, nothing to update

        # Send WebSocket update if the reply is in a community post
        if isinstance(post, CommunityPost):
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"community_{post.community.slug}",
                {
                    'type': 'rating_update',
                    'data': {
                        'post_id': post.id,
                        'comment_id': reply.comment.id,
                        'reply_id': reply.id,
                        'rating': float(reply.rating),
                        'total_ratings': reply.total_ratings,
                        'user_rating': None
                    }
                }
            )
    except (ObjectDoesNotExist, AttributeError, CommunityPost.DoesNotExist) as e:
        # Post, comment, or related object does not exist; skip update
        logger.warning(f"update_reply_rating_on_delete: Skipping update due to missing related object: {e}")
        return

@receiver(post_save, sender=Comment)
def update_post_comment_count(sender, instance, created, **kwargs):
    post = instance.personal_post or instance.community_post
    post.comment_count = post.comments.count()
    post.save()

    # Send WebSocket update if it's a community post
    if isinstance(post, CommunityPost):
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"community_{post.community.slug}",
            {
                'type': 'comment_update',
                'data': {
                    'action': 'create' if created else 'update',
                    'post_id': post.id,
                    'comment': {
                        'id': instance.id,
                        'author': {
                            'name': instance.author.get_full_name() or instance.author.username,
                            'username': instance.author.username,
                            'avatarUrl': instance.author.avatar.url if instance.author.avatar else None,
                            'personalityTags': []
                        },
                        'content': instance.content,
                        'timestamp': instance.created_at.isoformat(),
                        'replies': [],
                        'is_top_comment': instance.is_top_comment,
                        'rating': float(instance.rating),
                        'ratingCount': instance.total_ratings,
                        'hasRated': False,
                        'sentiment': 'neutral'
                    }
                }
            }
        )

@receiver(post_delete, sender=Comment)
def update_post_comment_count_on_delete(sender, instance, **kwargs):
    try:
        # Store necessary information before deletion
        post = instance.personal_post or instance.community_post
        post_id = post.id
        community_slug = post.community.slug if isinstance(post, CommunityPost) else None
        is_community_post = isinstance(post, CommunityPost)

        # Update post comment count
        post.comment_count = post.comments.count()
        post.save()

        # Send WebSocket update if it's a community post
        if is_community_post:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"community_{community_slug}",
                {
                    'type': 'comment_update',
                    'data': {
                        'action': 'delete',
                        'post_id': post_id,
                        'comment': None
                    }
                }
            )
    except Exception as e:
        logger.error(f"Error in comment deletion signal handler: {str(e)}", exc_info=True)

@receiver(post_delete, sender=Reply)
def handle_reply_deletion(sender, instance, **kwargs):
    try:
        # Store necessary information before deletion
        post = instance.comment.personal_post or instance.comment.community_post
        post_id = post.id
        comment_id = instance.comment.id
        reply_id = instance.id
        community_slug = post.community.slug if isinstance(post, CommunityPost) else None

        # Send WebSocket update if the reply is in a community post
        if isinstance(post, CommunityPost):
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"community_{community_slug}",
                {
                    'type': 'reply_deleted',
                    'data': {
                        'post_id': post_id,
                        'comment_id': comment_id,
                        'reply_id': reply_id
                    }
                }
            )
    except Exception as e:
        logger.error(f"Error in reply deletion signal: {str(e)}")

class Event(models.Model):
    EVENT_TYPES = [
        ('discussion', 'Discussion'),
        ('ama', 'Ask Me Anything'),
        ('challenge', 'Challenge')
    ]

    STATUS_CHOICES = [
        ('upcoming', 'Upcoming'),
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ]

    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name='events')
    title = models.CharField(max_length=200)
    description = models.TextField()
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    max_participants = models.PositiveIntegerField(null=True, blank=True)
    participants_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='upcoming')
    is_active = models.BooleanField(default=True)
    settings = models.JSONField(default=dict)  # Event-specific settings

    class Meta:
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['community', 'start_date']),
            models.Index(fields=['status', 'is_active']),
        ]

    def save(self, *args, **kwargs):
        # Update status based on dates
        now = timezone.now()
        if self.start_date > now:
            self.status = 'upcoming'
        elif self.end_date < now:
            self.status = 'completed'
        elif self.start_date <= now <= self.end_date:
            self.status = 'ongoing'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} - {self.community.name}"

class EventParticipant(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)
    is_attending = models.BooleanField(default=True)

    class Meta:
        unique_together = ['event', 'user']

    def __str__(self):
        return f"{self.user.username} - {self.event.title}"

class SavedPost(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_posts')
    personal_post = models.ForeignKey(PersonalPost, on_delete=models.CASCADE, related_name='saved_by', null=True, blank=True)
    community_post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name='saved_by', null=True, blank=True)
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-saved_at']
        unique_together = [
            ('user', 'personal_post'),
            ('user', 'community_post')
        ]

    def clean(self):
        """Validate that exactly one post is set"""
        if bool(self.personal_post) == bool(self.community_post):
            raise ValidationError('Exactly one of personal_post or community_post must be set')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        post = self.personal_post or self.community_post
        return f"Saved post {post.title} by {self.user.username}"
