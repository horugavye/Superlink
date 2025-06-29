from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from notifications.models import Notification, NotificationPreference
from connections.models import Connection, ConnectionRequest, UserSuggestion
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from community.models import PostRating

User = get_user_model()

def get_community_models():
    """Get community app models after Django has loaded all models."""
    from django.apps import apps
    return {
        # 'Post': apps.get_model('community', 'Post'),  # Removed, does not exist
        'Community': apps.get_model('community', 'Community'),
        'Comment': apps.get_model('community', 'Comment'),
        'CommunityPostRating': apps.get_model('community', 'PostRating'),
        'CommunityCommentRating': apps.get_model('community', 'CommentRating'),
        'CommunityReplyRating': apps.get_model('community', 'ReplyRating'),
    }

class ChatMessage(models.Model):
    """Stores the conversation history between users and the AI assistant."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assistant_chats')
    message = models.TextField()
    is_user_message = models.BooleanField(default=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    context = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)  # Add metadata field
    community = models.ForeignKey('community.Community', on_delete=models.SET_NULL, null=True, blank=True, related_name='assistant_chats')
    personal_post = models.ForeignKey('community.PersonalPost', on_delete=models.SET_NULL, null=True, blank=True, related_name='assistant_chats')
    community_post = models.ForeignKey('community.CommunityPost', on_delete=models.SET_NULL, null=True, blank=True, related_name='assistant_chats')
    comment = models.ForeignKey('community.Comment', on_delete=models.SET_NULL, null=True, blank=True, related_name='assistant_chats')
    conversation_id = models.CharField(max_length=100, null=True, blank=True)
    response = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['community', 'timestamp']),
            models.Index(fields=['personal_post', 'timestamp']),
            models.Index(fields=['community_post', 'timestamp']),
            models.Index(fields=['conversation_id']),
        ]

    def __str__(self):
        return f"{self.user.username}: {self.message[:50]}..."

class UserInterest(models.Model):
    """Stores vector representations of user interests for matching and recommendations."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assistant_interests')
    interest = models.CharField(max_length=100)  # e.g., "urban design", "quantum computing"
    vector = ArrayField(models.FloatField(), size=1536)  # Using OpenAI's embedding dimension
    weight = models.FloatField(default=1.0)  # How important this interest is to the user
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'interest']
        indexes = [
            models.Index(fields=['user', 'interest']),
        ]

class AssistantNotification(models.Model):
    """Model for assistant-specific notifications and recommendations."""
    NOTIFICATION_TYPES = [
        ('interest_match', 'Interest Match'),
        ('community_suggestion', 'Community Suggestion'),
        ('content_recommendation', 'Content Recommendation'),
        ('learning_insight', 'Learning Insight'),
        ('activity_summary', 'Activity Summary'),
        ('connection_suggestion', 'Connection Suggestion'),
        ('skill_development', 'Skill Development'),
        ('achievement_progress', 'Achievement Progress'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assistant_notifications')
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    priority = models.IntegerField(default=0)
    action_required = models.BooleanField(default=False)
    action_taken = models.BooleanField(default=False)
    
    # Generic relation to the related object
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Additional data for the assistant
    context = models.JSONField(default=dict, blank=True)
    confidence_score = models.FloatField(default=0.0)
    feedback = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', 'created_at']),
            models.Index(fields=['notification_type', 'priority']),
        ]

    def __str__(self):
        return f"{self.notification_type} - {self.user.username}"

    def create_notification(self):
        """Create a corresponding Notification object for the user."""
        # Check user's notification preferences
        try:
            prefs = self.user.notification_preferences
            should_notify = getattr(prefs, f'in_app_{self.notification_type}', True)
        except NotificationPreference.DoesNotExist:
            should_notify = True

        if should_notify:
            Notification.objects.create(
                recipient=self.user,
                notification_type='message',  # Using 'message' type for assistant notifications
                title=self.title,
                message=self.message,
                data={
                    'assistant_notification_id': self.id,
                    'notification_type': self.notification_type,
                    'priority': self.priority,
                    'action_required': self.action_required,
                    'context': self.context
                }
            )

    def mark_as_read(self):
        """Mark both assistant notification and corresponding notification as read."""
        self.is_read = True
        self.save(update_fields=['is_read'])
        # Also mark the corresponding notification as read
        Notification.objects.filter(
            recipient=self.user,
            data__assistant_notification_id=self.id
        ).update(is_read=True)

    def record_feedback(self, feedback_type, feedback_data):
        """Record user feedback about the notification."""
        self.feedback[feedback_type] = {
            'data': feedback_data,
            'timestamp': models.DateTimeField(auto_now=True)
        }
        self.save(update_fields=['feedback'])

class AIRatingInsight(models.Model):
    """AI-powered insights and analysis for ratings."""
    # Generic relation to the rated object (post, comment, or reply)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # AI analysis
    sentiment_score = models.FloatField(default=0.0)  # Overall sentiment of ratings
    rating_patterns = models.JSONField(default=dict)  # Patterns in how users rate
    quality_indicators = models.JSONField(default=dict)  # AI-detected quality indicators
    engagement_prediction = models.FloatField(default=0.0)  # Predicted future engagement
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['sentiment_score']),
        ]

    def __str__(self):
        return f"AI Insights for {self.content_type.model} {self.object_id}"

class RatingPattern(models.Model):
    """Tracks patterns in how users rate content."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rating_patterns')
    pattern_type = models.CharField(max_length=50)  # e.g., 'generous', 'critical', 'balanced'
    confidence = models.FloatField(default=0.0)  # AI confidence in this pattern
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    pattern_data = models.JSONField(default=dict)  # Detailed pattern data
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'pattern_type']),
        ]

    def __str__(self):
        return f"{self.user.username}'s {self.pattern_type} rating pattern"

class AssistantMemory(models.Model):
    """Stores the AI assistant's learning and context data for each user."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='assistant_memory')
    personality_profile = models.JSONField(default=dict)
    learning_data = models.JSONField(default=dict)
    context_window = models.JSONField(default=list)
    message_history = models.JSONField(default=list)
    community_engagement = models.JSONField(default=dict)
    # Track user's content preferences
    content_preferences = models.JSONField(default=dict)
    # Track user's interaction patterns
    interaction_patterns = models.JSONField(default=dict)
    # Add notification preferences
    notification_preferences = models.JSONField(default=dict)
    notification_frequency = models.CharField(
        max_length=20,
        choices=[
            ('realtime', 'Real-time'),
            ('daily', 'Daily Digest'),
            ('weekly', 'Weekly Summary'),
            ('custom', 'Custom')
        ],
        default='realtime'
    )
    notification_quiet_hours = models.JSONField(
        default=dict,
        help_text="Store quiet hours preferences in 24-hour format"
    )
    notification_priority_threshold = models.IntegerField(
        default=0,
        help_text="Minimum priority level for notifications"
    )
    
    # Add AI suggestion tracking
    suggestion_preferences = models.JSONField(default=dict)  # User preferences for suggestions
    suggestion_history = models.JSONField(default=dict)  # Track suggestion performance
    learning_preferences = models.JSONField(default=dict)
    
    # Add interest alchemy tracking
    interest_alchemy_preferences = models.JSONField(default=dict)  # User preferences for interest combinations
    curiosity_profile = models.JSONField(default=dict)  # Track user's curiosity patterns
    discovery_history = models.JSONField(default=dict)  # Track discoveries and insights
    
    # Add rating analysis tracking
    rating_insights = models.JSONField(default=dict)  # Store insights about user's rating patterns
    rating_preferences = models.JSONField(default=dict)  # User's preferences for rating types
    
    # Add last interaction tracking
    last_interaction = models.DateTimeField(auto_now=True, help_text="Last time the user interacted with the assistant")
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'last_interaction']),
        ]

    def update_context_window(self, message, is_user_message=True, max_size=10):
        """Update both the context window and message history with new message."""
        from django.utils import timezone
        
        # Create message entry with metadata
        message_entry = {
            'message': message,
            'is_user_message': is_user_message,
            'timestamp': timezone.now().isoformat(),
            'metadata': {
                'personality_profile': self.personality_profile,
                'learning_data': self.learning_data,
                'community_engagement': self.community_engagement,
                'content_preferences': self.content_preferences,
                'interaction_patterns': self.interaction_patterns
            }
        }
        
        # Update context window (recent messages)
        self.context_window.append(message_entry)
        if len(self.context_window) > max_size:
            self.context_window = self.context_window[-max_size:]
            
        # Update message history (all messages)
        self.message_history.append(message_entry)
        
        # Update learning data based on message
        self._update_learning_data(message, is_user_message)
        
        self.save()

    def _update_learning_data(self, message, is_user_message):
        """Update learning data based on message content."""
        # Update interaction patterns
        if 'interaction_patterns' not in self.learning_data:
            self.learning_data['interaction_patterns'] = {}
            
        # Track message frequency
        hour = timezone.now().hour
        if 'message_frequency' not in self.learning_data['interaction_patterns']:
            self.learning_data['interaction_patterns']['message_frequency'] = {}
        if str(hour) not in self.learning_data['interaction_patterns']['message_frequency']:
            self.learning_data['interaction_patterns']['message_frequency'][str(hour)] = 0
        self.learning_data['interaction_patterns']['message_frequency'][str(hour)] += 1
        
        # Track message types
        if 'message_types' not in self.learning_data['interaction_patterns']:
            self.learning_data['interaction_patterns']['message_types'] = {}
        message_type = 'user' if is_user_message else 'assistant'
        if message_type not in self.learning_data['interaction_patterns']['message_types']:
            self.learning_data['interaction_patterns']['message_types'][message_type] = 0
        self.learning_data['interaction_patterns']['message_types'][message_type] += 1
        
        # Update personality profile based on message content
        if is_user_message:
            self._update_personality_profile(message)

    def _update_personality_profile(self, message):
        """Update personality profile based on message content."""
        # Initialize personality profile if not exists
        if not self.personality_profile:
            self.personality_profile = {
                'communication_style': {},
                'interests': {},
                'preferences': {},
                'behavior_patterns': {}
            }
            
        # Update communication style
        if 'communication_style' not in self.personality_profile:
            self.personality_profile['communication_style'] = {}
            
        # Track message length patterns
        message_length = len(message)
        if 'message_length' not in self.personality_profile['communication_style']:
            self.personality_profile['communication_style']['message_length'] = {
                'short': 0,  # < 50 chars
                'medium': 0,  # 50-200 chars
                'long': 0    # > 200 chars
            }
            
        if message_length < 50:
            self.personality_profile['communication_style']['message_length']['short'] += 1
        elif message_length < 200:
            self.personality_profile['communication_style']['message_length']['medium'] += 1
        else:
            self.personality_profile['communication_style']['message_length']['long'] += 1

    def get_message_history(self, limit=None):
        """Get message history, optionally limited to the most recent messages."""
        if limit:
            return self.message_history[-limit:]
        return self.message_history

    def get_recent_context(self, n=5):
        """Get the n most recent messages from the context window."""
        return self.context_window[-n:] if self.context_window else []

    def update_community_engagement(self, community_id, engagement_type, value=1):
        """Update engagement metrics for a specific community."""
        if str(community_id) not in self.community_engagement:
            self.community_engagement[str(community_id)] = {
                'posts': 0,
                'comments': 0,
                'reactions': 0,
                'active_days': 0,
                'last_active': None
            }
        self.community_engagement[str(community_id)][engagement_type] += value
        self.save()

    def update_content_preferences(self, content_type, topic, value=1):
        """Update content preferences based on user interactions."""
        if content_type not in self.content_preferences:
            self.content_preferences[content_type] = {}
        if topic not in self.content_preferences[content_type]:
            self.content_preferences[content_type][topic] = 0
        self.content_preferences[content_type][topic] += value
        self.save()

    def update_notification_preferences(self, preferences):
        """Update assistant-specific notification preferences."""
        self.notification_preferences.update(preferences)
        self.save(update_fields=['notification_preferences'])

    def should_notify(self, notification_type, priority):
        """Determine if a notification should be sent based on preferences."""
        if priority < self.notification_priority_threshold:
            return False
            
        # Check quiet hours
        current_hour = timezone.now().hour
        if str(current_hour) in self.notification_quiet_hours.get('hours', []):
            return False
            
        # Check notification type preferences
        return self.notification_preferences.get(notification_type, True)

    def create_notification(self, notification_type, title, message, priority=0, context=None):
        """Create a new assistant notification if it meets the user's preferences."""
        if self.should_notify(notification_type, priority):
            notification = AssistantNotification.objects.create(
                user=self.user,
                notification_type=notification_type,
                title=title,
                message=message,
                priority=priority,
                context=context or {}
            )
            notification.create_notification()
            return notification
        return None

    def update_suggestion_preferences(self, preferences):
        """Update user's preferences for AI suggestions."""
        self.suggestion_preferences.update(preferences)
        self.save(update_fields=['suggestion_preferences'])
    
    def record_suggestion_feedback(self, suggestion_type, suggestion_id, feedback):
        """Record user feedback for an AI suggestion."""
        if suggestion_type not in self.suggestion_history:
            self.suggestion_history[suggestion_type] = {}
        
        self.suggestion_history[suggestion_type][str(suggestion_id)] = {
            'feedback': feedback,
            'timestamp': timezone.now().isoformat()
        }
        self.save(update_fields=['suggestion_history'])
    
    def get_suggestion_insights(self, suggestion_type):
        """Get insights about suggestion performance for a specific type."""
        if suggestion_type not in self.suggestion_history:
            return None
            
        history = self.suggestion_history[suggestion_type]
        total = len(history)
        if total == 0:
            return None
            
        positive = sum(1 for feedback in history.values() if feedback.get('feedback', {}).get('positive', False))
        negative = sum(1 for feedback in history.values() if feedback.get('feedback', {}).get('negative', False))
        
        return {
            'total_suggestions': total,
            'positive_rate': positive / total if total > 0 else 0,
            'negative_rate': negative / total if total > 0 else 0,
            'neutral_rate': (total - positive - negative) / total if total > 0 else 0,
            'last_feedback': max(history.values(), key=lambda x: x['timestamp']) if history else None
        }

    def record_curiosity_collision(self, interests, impact_score, insights):
        """Record a new curiosity collision."""
        collision = CuriosityCollision.objects.create(
            user=self.user,
            impact_score=impact_score,
            insights=insights
        )
        collision.interests.set(interests)
        
        # Update discovery history
        self.discovery_history[str(collision.id)] = {
            'timestamp': timezone.now().isoformat(),
            'impact_score': impact_score,
            'insights': insights
        }
        self.save(update_fields=['discovery_history'])
        
        return collision

    def suggest_interest_alchemy(self):
        """Suggest new interest combinations based on user's profile."""
        # This would be implemented in the AI service layer
        pass

    def update_rating_insights(self, rating_type, rating_data):
        """Update insights about user's rating patterns."""
        if rating_type not in self.rating_insights:
            self.rating_insights[rating_type] = []
            
        self.rating_insights[rating_type].append({
            'data': rating_data,
            'timestamp': timezone.now().isoformat()
        })
        
        # Keep only the last 100 insights
        if len(self.rating_insights[rating_type]) > 100:
            self.rating_insights[rating_type] = self.rating_insights[rating_type][-100:]
            
        self.save(update_fields=['rating_insights'])
    
    def get_rating_patterns(self, rating_type=None):
        """Get insights about user's rating patterns."""
        if rating_type:
            return self.rating_insights.get(rating_type, [])
        return self.rating_insights

@receiver(post_save, sender=User)
def create_assistant_memory(sender, instance, created, **kwargs):
    """Create AssistantMemory when a new user is created."""
    if created:
        AssistantMemory.objects.create(user=instance)

@receiver(post_save, sender=AssistantNotification)
def handle_assistant_notification(sender, instance, created, **kwargs):
    """Handle new assistant notifications."""
    if created:
        memory = instance.user.assistant_memory
        notification_patterns = memory.interaction_patterns.get('notifications', {})
        notification_patterns[instance.notification_type] = notification_patterns.get(instance.notification_type, 0) + 1
        hour = instance.created_at.hour
        time_patterns = notification_patterns.get('time_patterns', {})
        time_patterns[str(hour)] = time_patterns.get(str(hour), 0) + 1
        
        memory.interaction_patterns['notifications'] = notification_patterns
        memory.save(update_fields=['interaction_patterns'])

class AssistantInterest(models.Model):
    """Stores vector representations of interests for matching and recommendations."""
    # Use existing UserInterest model from users app for basic interest storage
    user_interest = models.ForeignKey('users.UserInterest', on_delete=models.CASCADE, related_name='assistant_data')
    vector = ArrayField(models.FloatField(), size=1536)  # Using OpenAI's embedding dimension
    weight = models.FloatField(default=1.0)  # How important this interest is to the user
    last_updated = models.DateTimeField(auto_now=True)
    # Track interest evolution
    evolution_history = models.JSONField(default=list)  # Track how interest has evolved over time
    # Track related interests
    related_interests = models.JSONField(default=list)  # Store related interests discovered through interactions
    
    class Meta:
        indexes = [
            models.Index(fields=['user_interest', 'last_updated']),
        ]

    def update_weight(self, new_weight):
        """Update interest weight and track evolution."""
        self.evolution_history.append({
            'timestamp': timezone.now().isoformat(),
            'old_weight': self.weight,
            'new_weight': new_weight
        })
        self.weight = new_weight
        self.save()

    def add_related_interest(self, interest_id, similarity_score):
        """Add a related interest with its similarity score."""
        self.related_interests.append({
            'interest_id': interest_id,
            'similarity_score': similarity_score,
            'discovered_at': timezone.now().isoformat()
        })
        self.save()

class AISuggestion(models.Model):
    """Base model for AI-powered suggestions."""
    SUGGESTION_TYPES = [
        ('post', 'Post'),
        ('community', 'Community'),
        ('connection', 'Connection'),
        ('content', 'Content'),
        ('skill', 'Skill'),
        ('interest', 'Interest'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='%(class)s_suggestions')
    suggestion_type = models.CharField(max_length=20, choices=SUGGESTION_TYPES)
    score = models.FloatField(default=0.0)
    confidence = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_rejected = models.BooleanField(default=False)
    rejected_at = models.DateTimeField(null=True, blank=True)
    
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    reasoning = models.JSONField(default=dict)
    features = models.JSONField(default=dict)
    user_feedback = models.JSONField(default=dict)
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['user', 'suggestion_type', 'score']),
            models.Index(fields=['content_type', 'object_id']),
        ]

class PostSuggestion(AISuggestion):
    """AI-powered post suggestions."""
    personal_post = models.ForeignKey('community.PersonalPost', on_delete=models.CASCADE, related_name='ai_suggestions', null=True, blank=True)
    community_post = models.ForeignKey('community.CommunityPost', on_delete=models.CASCADE, related_name='ai_suggestions', null=True, blank=True)
    relevance_factors = models.JSONField(default=dict)  # Factors that made the post relevant
    engagement_prediction = models.FloatField(default=0.0)  # Predicted engagement score
    content_similarity = models.FloatField(default=0.0)  # Similarity to user's interests
    user_history_impact = models.FloatField(default=0.0)  # Impact of user's history
    
    class Meta:
        unique_together = [
            ('user', 'personal_post'),
            ('user', 'community_post')
        ]
        ordering = ['-score', '-confidence']

    def clean(self):
        """Validate that exactly one post type is set."""
        if bool(self.personal_post) == bool(self.community_post):
            raise ValidationError('Exactly one of personal_post or community_post must be set.')

    @property
    def post(self):
        """Return the actual post object regardless of type."""
        return self.personal_post or self.community_post

class CommunitySuggestion(AISuggestion):
    """AI-powered community suggestions."""
    community = models.ForeignKey('community.Community', on_delete=models.CASCADE, related_name='ai_suggestions')
    member_similarity = models.FloatField(default=0.0)  # Similarity to existing members
    activity_match = models.FloatField(default=0.0)  # Match with user's activity patterns
    growth_potential = models.FloatField(default=0.0)  # Predicted value to the community
    topic_relevance = models.FloatField(default=0.0)  # Relevance to user's interests
    
    class Meta:
        unique_together = ('user', 'community')
        ordering = ['-score', '-confidence']

class ConnectionSuggestion(AISuggestion):
    """AI-powered connection suggestions."""
    suggested_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_connection_suggestions')
    mutual_connections = models.IntegerField(default=0)
    interest_overlap = models.FloatField(default=0.0)
    activity_compatibility = models.FloatField(default=0.0)
    communication_style_match = models.FloatField(default=0.0)
    potential_collaboration_score = models.FloatField(default=0.0)
    
    # Enhanced fields for Interest Alchemy integration
    complementary_interests = models.JSONField(default=dict, help_text="Store Interest Alchemy pairs that connect the users")
    curiosity_collisions = models.JSONField(default=list, help_text="Store relevant Curiosity Collisions between users")
    micro_community_overlap = models.JSONField(default=dict, help_text="Track shared micro-community memberships")
    interest_alchemy_score = models.FloatField(default=0.0, help_text="Score based on Interest Alchemy compatibility")
    
    class Meta:
        unique_together = ('user', 'suggested_user')
        ordering = ['-score', '-confidence']

    def calculate_interest_alchemy_score(self):
        """Calculate a score based on Interest Alchemy compatibility."""
        # Get Interest Alchemy pairs that connect both users
        user_interests = set(self.user.interests.all())
        suggested_user_interests = set(self.suggested_user.interests.all())
        
        # Find Interest Alchemy pairs that connect their interests
        alchemy_pairs = InterestAlchemy.objects.filter(
            models.Q(interest1__in=user_interests, interest2__in=suggested_user_interests) |
            models.Q(interest1__in=suggested_user_interests, interest2__in=user_interests)
        )
        
        # Calculate score based on complementarity and discovery potential
        total_score = 0
        for pair in alchemy_pairs:
            total_score += (pair.complementarity_score * 0.7 + pair.discovery_potential * 0.3)
        
        # Store the pairs and score
        self.complementary_interests = {
            str(pair.id): {
                'complementarity_score': pair.complementarity_score,
                'discovery_potential': pair.discovery_potential,
                'interests': [pair.interest1.interest, pair.interest2.interest]
            }
            for pair in alchemy_pairs
        }
        self.interest_alchemy_score = total_score / max(1, len(alchemy_pairs))
        
        # Find Curiosity Collisions
        collisions = CuriosityCollision.objects.filter(
            models.Q(user=self.user, interests__in=suggested_user_interests) |
            models.Q(user=self.suggested_user, interests__in=user_interests)
        ).distinct()
        
        self.curiosity_collisions = [
            {
                'id': collision.id,
                'impact_score': collision.impact_score,
                'insights': collision.insights
            }
            for collision in collisions
        ]
        
        # Find shared micro-communities
        user_micro_communities = set(self.user.micro_communities.all())
        suggested_user_micro_communities = set(self.suggested_user.micro_communities.all())
        shared_communities = user_micro_communities.intersection(suggested_user_micro_communities)
        
        self.micro_community_overlap = {
            str(community.id): {
                'name': community.name,
                'activity_score': community.activity_score,
                'members_count': community.members_count
            }
            for community in shared_communities
        }
        
        self.save()
        return self.interest_alchemy_score

    def create_connection_request(self, message=""):
        """Create a connection request with enhanced Interest Alchemy data."""
        if not self.is_active or self.is_rejected:
            return None
            
        # Calculate Interest Alchemy score if not already done
        if not self.interest_alchemy_score:
            self.calculate_interest_alchemy_score()
            
        # Create connection request with enhanced data
        request = ConnectionRequest.objects.create(
            sender=self.user,
            receiver=self.suggested_user,
            message=message,
            match_score=self.score,
            connection_strength=self.score * 100,
            common_interests=self.reasoning.get('common_interests', []),
            match_highlights=self.reasoning.get('match_highlights', []),
            # Add Interest Alchemy data
            data={
                'interest_alchemy_score': self.interest_alchemy_score,
                'complementary_interests': self.complementary_interests,
                'curiosity_collisions': self.curiosity_collisions,
                'micro_community_overlap': self.micro_community_overlap
            }
        )
        
        # Deactivate this suggestion
        self.is_active = False
        self.save()
        
        return request

class ContentRecommendation(AISuggestion):
    """AI-powered content recommendations."""
    title = models.CharField(max_length=255)
    description = models.TextField()
    url = models.URLField()
    source = models.CharField(max_length=100)
    engagement_metrics = models.JSONField(default=dict)
    content_vector = ArrayField(models.FloatField(), size=1536)
    
    class Meta:
        ordering = ['-score', '-confidence']

class SkillRecommendation(AISuggestion):
    """AI-powered skill development recommendations."""
    skill_name = models.CharField(max_length=100)
    current_level = models.FloatField(default=0.0)
    target_level = models.FloatField(default=0.0)
    learning_path = models.JSONField(default=list)
    resources = models.JSONField(default=list)
    estimated_time = models.IntegerField(default=0)  # in hours
    priority = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-priority', '-score']

# Add signals for AI suggestions
@receiver(post_save, sender=ConnectionSuggestion)
def handle_connection_suggestion(sender, instance, created, **kwargs):
    """Handle new connection suggestions."""
    if created:
        # Create a notification for the suggestion
        memory = instance.user.assistant_memory
        memory.create_notification(
            notification_type='connection_suggestion',
            title='New Connection Suggestion',
            message=f"We think you might connect well with {instance.suggested_user.get_full_name()}",
            priority=instance.score * 100,  # Convert to 0-100 scale
            context={
                'suggestion_id': instance.id,
                'match_score': instance.score,
                'common_interests': instance.reasoning.get('common_interests', []),
                'match_highlights': instance.reasoning.get('match_highlights', [])
            }
        )

@receiver(post_save, sender=CommunitySuggestion)
def handle_community_suggestion(sender, instance, created, **kwargs):
    """Handle new community suggestions."""
    if created:
        memory = instance.user.assistant_memory
        memory.create_notification(
            notification_type='community_suggestion',
            title='New Community Suggestion',
            message=f"You might be interested in the {instance.community.name} community",
            priority=instance.score * 100,
            context={
                'suggestion_id': instance.id,
                'match_score': instance.score,
                'topic_relevance': instance.topic_relevance,
                'member_similarity': instance.member_similarity
            }
        )

@receiver(post_save, sender=PostSuggestion)
def handle_post_suggestion(sender, instance, created, **kwargs):
    """Handle new post suggestions."""
    if created:
        memory = instance.user.assistant_memory
        memory.create_notification(
            notification_type='content_recommendation',
            title='Recommended Post',
            message=f"We found a post you might be interested in: {instance.post.title}",
            priority=instance.score * 100,
            context={
                'suggestion_id': instance.id,
                'match_score': instance.score,
                'engagement_prediction': instance.engagement_prediction,
                'content_similarity': instance.content_similarity
            }
        )

# Add signals to enhance community ratings with AI insights
@receiver(post_save, sender='community.PostRating')
def update_community_score(sender, instance, created, **kwargs):
    """Update community score when a new rating is added."""
    from django.apps import apps
    CommunityScore = apps.get_model('assistant', 'CommunityScore')
    post = instance.personal_post or instance.community_post
    if hasattr(post, 'personalpost') or post.__class__.__name__ == 'PersonalPost':
        score, _ = CommunityScore.objects.get_or_create(personal_post=post)
    else:
        score, _ = CommunityScore.objects.get_or_create(community_post=post)
    score.update_scores()

@receiver(post_save, sender='community.PostRating')
def analyze_post_rating(sender, instance, created, **kwargs):
    """Analyze post ratings with AI when new ratings are added."""
    from django.apps import apps
    models = get_community_models()
    AIRatingInsight = apps.get_model('assistant', 'AIRatingInsight')
    RatingPattern = apps.get_model('assistant', 'RatingPattern')
    
    post = instance.personal_post or instance.community_post
    if not post:
        return
        
    # Get or create AI insights
    insight, _ = AIRatingInsight.objects.get_or_create(
        content_type=ContentType.objects.get_for_model(post),
        object_id=post.id
    )
    
    # Update insights based on all ratings
    ratings = models['CommunityPostRating'].objects.filter(
        personal_post=post if hasattr(post, 'personal_post') else None,
        community_post=post if hasattr(post, 'community_post') else None
    )
    
    # ... rest of the function remains the same ...

# Similar signals for comment and reply ratings
@receiver(post_save, sender='community.CommentRating')
def analyze_comment_rating(sender, instance, created, **kwargs):
    """Analyze comment ratings with AI."""
    insight, _ = AIRatingInsight.objects.get_or_create(
        content_type=ContentType.objects.get_for_model(instance.comment),
        object_id=instance.comment.id
    )
    # Similar analysis as post ratings
    # ... (implement similar logic for comments)

@receiver(post_save, sender='community.ReplyRating')
def analyze_reply_rating(sender, instance, created, **kwargs):
    """Analyze reply ratings with AI."""
    insight, _ = AIRatingInsight.objects.get_or_create(
        content_type=ContentType.objects.get_for_model(instance.reply),
        object_id=instance.reply.id
    )
    # Similar analysis as post ratings
    # ... (implement similar logic for replies)

class CommunityScore(models.Model):
    """Tracks community-wide post scores and metrics."""
    personal_post = models.OneToOneField('community.PersonalPost', on_delete=models.CASCADE, related_name='community_score', null=True, blank=True)
    community_post = models.OneToOneField('community.CommunityPost', on_delete=models.CASCADE, related_name='community_score', null=True, blank=True)
    total_ratings = models.IntegerField(default=0)
    average_score = models.FloatField(default=0.0)
    rating_distribution = models.JSONField(default=dict)  # Distribution of different rating types
    engagement_score = models.FloatField(default=0.0)  # Overall engagement metric
    quality_score = models.FloatField(default=0.0)  # AI-calculated quality score
    trending_score = models.FloatField(default=0.0)  # Trending metric
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['average_score', 'engagement_score']),
            models.Index(fields=['trending_score']),
        ]

    def clean(self):
        """Validate that exactly one post type is set."""
        if bool(self.personal_post) == bool(self.community_post):
            raise ValidationError('Exactly one of personal_post or community_post must be set.')

    @property
    def post(self):
        """Return the actual post object regardless of type."""
        return self.personal_post or self.community_post

    def update_scores(self):
        """Update all scores based on current ratings."""
        post = self.post
        if not post:
            return
        
        ratings = post.ratings.all()
        if not ratings:
            return
        
        # Calculate average score
        self.total_ratings = ratings.count()
        self.average_score = sum(r.rating for r in ratings) / self.total_ratings
        
        # Calculate rating distribution (single type, since no rating_type field)
        distribution = {
            'overall': {
                'count': self.total_ratings,
                'average': self.average_score
            }
        }
        self.rating_distribution = distribution
        
        # Update engagement score (weighted combination of various factors)
        self.engagement_score = (
            self.average_score * 0.4 +
            (post.comment_count / max(1, self.total_ratings)) * 0.3 +
            (post.view_count / max(1, self.total_ratings)) * 0.3
        )
        
        self.save()

class InterestAlchemy(models.Model):
    """Tracks and manages complementary interest pairings."""
    interest1 = models.ForeignKey('users.UserInterest', on_delete=models.CASCADE, related_name='alchemy_as_primary')
    interest2 = models.ForeignKey('users.UserInterest', on_delete=models.CASCADE, related_name='alchemy_as_secondary')
    complementarity_score = models.FloatField(default=0.0)  # How well these interests complement each other
    discovery_potential = models.FloatField(default=0.0)  # Potential for new insights
    created_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    success_metrics = models.JSONField(default=dict)  # Track success of this pairing
    micro_communities = models.JSONField(default=list)  # List of micro-communities created from this pairing
    
    class Meta:
        unique_together = ('interest1', 'interest2')
        indexes = [
            models.Index(fields=['complementarity_score']),
            models.Index(fields=['discovery_potential']),
        ]

    def __str__(self):
        return f"Alchemy: {self.interest1.name} + {self.interest2.name}"

class MicroCommunity(models.Model):
    """Represents communities created from interest alchemy."""
    name = models.CharField(max_length=100)
    description = models.TextField()
    parent_community = models.ForeignKey('community.Community', on_delete=models.CASCADE, related_name='micro_communities')
    interest_alchemy = models.ForeignKey(InterestAlchemy, on_delete=models.CASCADE, related_name='communities')
    created_at = models.DateTimeField(auto_now_add=True)
    members_count = models.IntegerField(default=0)
    activity_score = models.FloatField(default=0.0)
    discovery_insights = models.JSONField(default=list)  # Track insights discovered in this community
    
    class Meta:
        verbose_name_plural = "Micro Communities"
        indexes = [
            models.Index(fields=['activity_score']),
            models.Index(fields=['members_count']),
        ]

    def __str__(self):
        return f"{self.name} (Micro-Community)"

class CuriosityCollision(models.Model):
    """Tracks unexpected but valuable connections between interests."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='curiosity_collisions')
    interests = models.ManyToManyField('users.UserInterest', related_name='collisions')
    discovered_at = models.DateTimeField(auto_now_add=True)
    impact_score = models.FloatField(default=0.0)  # How impactful this collision was
    insights = models.JSONField(default=list)  # Insights gained from this collision
    follow_up_actions = models.JSONField(default=list)  # Actions taken based on this collision
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'discovered_at']),
            models.Index(fields=['impact_score']),
        ]

    def __str__(self):
        return f"Curiosity Collision for {self.user.username}"

@receiver(post_save, sender=InterestAlchemy)
def handle_interest_alchemy(sender, instance, created, **kwargs):
    """Handle new interest alchemy combinations."""
    if created:
        # Notify relevant users about this new combination
        for user in User.objects.filter(
            interests__in=[instance.interest1, instance.interest2]
        ).distinct():
            memory = user.assistant_memory
            memory.create_notification(
                notification_type='interest_alchemy',
                title='New Interest Combination Discovered',
                message=f"Discover the intersection of {instance.interest1.name} and {instance.interest2.name}",
                priority=instance.complementarity_score * 100,
                context={
                    'alchemy_id': instance.id,
                    'complementarity_score': instance.complementarity_score,
                    'discovery_potential': instance.discovery_potential
                }
            )
