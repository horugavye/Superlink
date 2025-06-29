from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.dispatch import receiver
from PIL import Image
import os
from stories.models import Story  # Add this import at the top

# Get the custom User model
User = settings.AUTH_USER_MODEL

class Group(models.Model):
    DEFAULT_GROUP_AVATAR = 'avatars/groudefault.jpeg'
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='group_avatars/', null=True, blank=True, default=DEFAULT_GROUP_AVATAR)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_groups')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_private = models.BooleanField(default=False)
    invite_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    max_members = models.PositiveIntegerField(default=100)
    rules = models.TextField(blank=True)
    settings = models.JSONField(default=dict)  # For storing group-specific settings
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_private']),
            models.Index(fields=['invite_code']),
        ]

    def __str__(self):
        return self.name

class Conversation(models.Model):
    CONVERSATION_TYPES = [
        ('direct', 'Direct Message'),
        ('group', 'Group Chat')
    ]
    
    type = models.CharField(max_length=10, choices=CONVERSATION_TYPES)
    name = models.CharField(max_length=255, null=True, blank=True)  # For group chats
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True, blank=True, related_name='conversations')
    # Add fields to track direct message participants
    participant1 = models.ForeignKey(User, on_delete=models.CASCADE, 
                                   null=True, blank=True, related_name='direct_conversations_as_p1')
    participant2 = models.ForeignKey(User, on_delete=models.CASCADE, 
                                   null=True, blank=True, related_name='direct_conversations_as_p2')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    last_message = models.ForeignKey('Message', null=True, blank=True, on_delete=models.SET_NULL, related_name='last_message_of')
    
    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['type', 'is_active']),
            models.Index(fields=['updated_at']),
            models.Index(fields=['group']),
            models.Index(fields=['participant1', 'participant2']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['participant1', 'participant2', 'type'],
                condition=models.Q(type='direct'),
                name='unique_direct_conversation'
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.type == 'direct':
            # Check if this is a new conversation
            if not self.pk:
                return
            
            # For direct messages, ensure there are exactly two members
            member_count = self.members.count()
            if member_count != 2:
                raise ValidationError('Direct message conversations must have exactly two members')
            
            # Ensure no group is associated with direct messages
            if self.group:
                raise ValidationError('Direct messages cannot be associated with a group')
            
            # Ensure both participants are set for direct messages
            if not (self.participant1 and self.participant2):
                raise ValidationError('Direct messages must have both participants set')
            
            # Ensure participants are different users
            if self.participant1 == self.participant2:
                raise ValidationError('Direct message participants must be different users')
            
            # Check for existing conversation between these participants
            existing = Conversation.objects.filter(
                type='direct',
                participant1__in=[self.participant1, self.participant2],
                participant2__in=[self.participant1, self.participant2]
            ).exclude(pk=self.pk).first()
            
            if existing:
                raise ValidationError('A conversation already exists between these participants')
        
        elif self.type == 'group':
            # For group chats without a group, ensure we have a name
            if not self.group and not self.name:
                raise ValidationError('Group chats without a group must have a name')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @classmethod
    def create_direct_message(cls, user1, user2):
        """
        Create a direct message conversation between two users.
        If a conversation already exists between these users, return that instead.
        """
        print(f"Creating direct message between {user1.username} and {user2.username}")
        
        # Check if a conversation already exists between these users
        existing_conversation = cls.objects.filter(
            type='direct',
            participant1=user1,
            participant2=user2
        ).first() or cls.objects.filter(
            type='direct',
            participant1=user2,
            participant2=user1
        ).first()
        
        if existing_conversation:
            print(f"Found existing conversation: {existing_conversation.id}")
            # Ensure both users are members
            if not existing_conversation.members.filter(user=user1).exists():
                ConversationMember.objects.create(conversation=existing_conversation, user=user1)
            if not existing_conversation.members.filter(user=user2).exists():
                ConversationMember.objects.create(conversation=existing_conversation, user=user2)
            return existing_conversation
        
        print("Creating new conversation...")
        conversation = cls.objects.create(
            type='direct',
            participant1=user1,
            participant2=user2
        )
        print(f"Created new conversation: {conversation.id}")
        
        # Add both users as members
        print("Creating conversation members...")
        ConversationMember.objects.create(conversation=conversation, user=user1)
        ConversationMember.objects.create(conversation=conversation, user=user2)
        print("Created conversation members")
        
        return conversation

    @classmethod
    def create_group_chat(cls, name, creator, initial_members=None):
        """
        Create a group chat conversation.
        If no group is specified, it will be a standalone group chat.
        """
        conversation = cls.objects.create(
            type='group',
            name=name
        )
        
        # Add creator as admin
        ConversationMember.objects.create(
            conversation=conversation,
            user=creator,
            role='admin'
        )
        
        # Add initial members if provided
        if initial_members:
            for member in initial_members:
                if member != creator:  # Skip creator as they're already added
                    ConversationMember.objects.create(
                        conversation=conversation,
                        user=member
                    )
        
        return conversation

    def get_participants(self):
        """Get all participants in the conversation"""
        if self.type == 'direct':
            return [self.participant1, self.participant2]
        return [member.user for member in self.members.all()]

    def is_participant(self, user):
        """Check if a user is a participant in the conversation"""
        if self.type == 'direct':
            return user in [self.participant1, self.participant2]
        return self.members.filter(user=user).exists()

    def __str__(self):
        if self.type == 'direct':
            p1_name = self.participant1.username if self.participant1 else 'Unknown'
            p2_name = self.participant2.username if self.participant2 else 'Unknown'
            return f"DM: {p1_name} ↔ {p2_name}"
        if self.group:
            return f"{self.group.name} ({self.type})"
        return f"{self.name} ({self.type})"

class ConversationMember(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('moderator', 'Moderator'),
        ('member', 'Member')
    ]
    
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read = models.DateTimeField(null=True, blank=True)
    is_muted = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    unread_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        unique_together = ['conversation', 'user']
        indexes = [
            models.Index(fields=['conversation', 'user']),
            models.Index(fields=['is_pinned']),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        # Only group conversations can have admins and moderators
        if self.conversation.type == 'direct' and self.role != 'member':
            raise ValidationError('Direct messages can only have member roles')
        
        # Check if this is the first member being added
        if not self.pk and self.conversation.members.exists():
            # For direct messages, ensure we don't exceed 2 members
            if self.conversation.type == 'direct' and self.conversation.members.count() >= 2:
                raise ValidationError('Direct messages can only have two members')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def has_permission(self, permission):
        """Check if member has specific permission based on role"""
        if self.role == 'admin':
            return True
        if self.role == 'moderator':
            return permission in ['delete_messages', 'pin_messages', 'mute_members']
        return permission in ['send_messages', 'react_messages']

    def __str__(self):
        return f"{self.user.username} - {self.conversation} ({self.role})"

class File(models.Model):
    FILE_TYPES = [
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('document', 'Document'),
        ('other', 'Other')
    ]
    
    # Common file extensions mapping
    EXTENSION_MAPPING = {
        # Images
        'image': ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg', 'tiff', 'ico', 'heic', 'heif'],
        # Videos
        'video': ['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm', 'm4v', '3gp', 'mpeg', 'mpg'],
        # Audio
        'audio': ['mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac', 'wma', 'aiff', 'mid', 'midi'],
        # Documents
        'document': [
            # Text documents
            'txt', 'rtf', 'doc', 'docx', 'odt', 'pages',
            # Spreadsheets
            'xls', 'xlsx', 'csv', 'ods', 'numbers',
            # Presentations
            'ppt', 'pptx', 'key', 'odp',
            # PDFs
            'pdf',
            # Archives
            'zip', 'rar', '7z', 'tar', 'gz', 'bz2',
            # Code files
            'py', 'js', 'html', 'css', 'php', 'java', 'cpp', 'c', 'h', 'ts', 'jsx', 'tsx',
            # Markup
            'md', 'markdown', 'xml', 'json', 'yaml', 'yml',
            # Other documents
            'epub', 'mobi', 'azw3', 'djvu'
        ]
    }
    
    file = models.FileField(upload_to='chat_attachments/')
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100)  # Will store file extension
    file_size = models.PositiveIntegerField()
    category = models.CharField(max_length=20, choices=FILE_TYPES)
    thumbnail = models.ImageField(upload_to='chat_attachments/thumbnails/', null=True, blank=True)
    duration = models.PositiveIntegerField(null=True, blank=True)  # For video/audio files
    created_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['file_name']),
            models.Index(fields=['file_type']),
            models.Index(fields=['category']),
            models.Index(fields=['created_at']),
        ]
    
    def save(self, *args, **kwargs):
        # Extract file extension from file_name
        if self.file_name:
            self.file_type = self.file_name.split('.')[-1].lower()
            # Set category based on file extension
            self.category = self.get_category_from_extension(self.file_type)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_category_from_extension(cls, extension):
        """Determine file category based on extension"""
        for category, extensions in cls.EXTENSION_MAPPING.items():
            if extension in extensions:
                return category
        return 'other'
    
    def get_url(self):
        """Get the full URL for the file"""
        if not self.file:
            return None
        # Get the file path relative to MEDIA_ROOT
        path = self.file.name
        # Remove any leading slashes
        path = path.lstrip('/')
        # Return the path as is - Django will handle the media URL prefix
        return path
    
    def get_thumbnail_url(self):
        """Get the full URL for the thumbnail"""
        if not self.thumbnail:
            return None
        # Get the thumbnail path relative to MEDIA_ROOT
        path = self.thumbnail.name
        # Remove any leading slashes
        path = path.lstrip('/')
        # Return the path as is - Django will handle the media URL prefix
        return path
    
    def __str__(self):
        return f"{self.file_name} ({self.category})"

@receiver(post_save, sender=File)
def generate_thumbnail(sender, instance, created, **kwargs):
    """Generate thumbnail for image files when they are created"""
    if created and instance.category == 'image' and not instance.thumbnail:
        try:
            # Open the image file
            with Image.open(instance.file.path) as img:
                # Convert to RGB if necessary (for PNG with transparency)
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    img = img.convert('RGB')
                
                # Calculate thumbnail size (max 200x200 while maintaining aspect ratio)
                max_size = (200, 200)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                # Create thumbnail filename
                thumb_name = f"thumb_{os.path.basename(instance.file.name)}"
                thumb_path = os.path.join('chat_attachments/thumbnails', thumb_name)
                
                # Save thumbnail
                img.save(instance.file.storage.path(thumb_path), 'JPEG', quality=85)
                
                # Update the thumbnail field
                instance.thumbnail = thumb_path
                instance.save(update_fields=['thumbnail'])
        except Exception as e:
            print(f"Error generating thumbnail for {instance.file_name}: {str(e)}")

class Message(models.Model):
    MESSAGE_TYPES = [
        ('text', 'Text'),
        ('image', 'Image'),
        ('file', 'File'),
        ('voice', 'Voice'),
        ('video', 'Video'),
        ('mixed', 'Mixed Content')  # For messages with both text and files
    ]
    
    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed')
    ]
    
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    story = models.ForeignKey(Story, null=True, blank=True, on_delete=models.SET_NULL, related_name='chat_messages')  # New field for story attachment
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(blank=True)  # Allow blank for file-only messages
    
    # Updated file relationship
    files = models.ManyToManyField(File, related_name='messages', blank=True)
    
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPES, default='text')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='sent')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_edited = models.BooleanField(default=False)
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='replies')
    thread = models.ForeignKey('MessageThread', null=True, blank=True, on_delete=models.SET_NULL, related_name='messages')
    is_pinned = models.BooleanField(default=False)
    is_forwarded = models.BooleanField(default=False)
    original_message = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='forwards')
    is_thread_reply = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['sender', 'created_at']),
            models.Index(fields=['is_pinned']),
            models.Index(fields=['message_type']),
        ]

    def clean(self):
        """Validate message content and type."""
        if not self.content and not (self.pk and self.files.exists()):
            raise ValidationError('Message must have content or files')
        
        if self.content and len(self.content.strip()) > 5000:
            raise ValidationError('Message content cannot exceed 5000 characters')
        
        # Validate message type
        if self.message_type not in dict(Message.MESSAGE_TYPES):
            raise ValidationError('Invalid message type')
        
        # Validate status
        if self.status not in dict(Message.STATUS_CHOICES):
            raise ValidationError('Invalid message status')
        
        # Validate reply_to is in the same conversation
        if self.reply_to and self.reply_to.conversation != self.conversation:
            raise ValidationError('Reply must be to a message in the same conversation')
        
        # Validate content and files based on message type
        has_files = False
        if self.pk:  # Only check files if the message has been saved
            has_files = self.files.exists()
        has_content = bool(self.content.strip())
        
        if self.message_type == 'text' and not has_content:
            raise ValidationError('Text messages must have content')
        
        if self.message_type in ['image', 'file', 'voice', 'video'] and not has_files:
            raise ValidationError(f'{self.message_type} messages must have files')
        
        if self.message_type == 'mixed' and not (has_content or has_files):
            raise ValidationError('Mixed content messages must have either text or files')

    def save(self, *args, **kwargs):
        is_new = self.pk is None  # Check if this is a new message
        
        # Determine message type based on content and files
        has_content = bool(self.content and self.content.strip())
        
        # Only check files if the message has an ID
        has_files = False
        if self.pk:
            has_files = self.files.exists()
        
        if has_files and has_content:
            self.message_type = 'mixed'
        elif has_files:
            # Determine file type from the first file
            first_file = self.files.first()
            if first_file:
                if first_file.category in ['image', 'video', 'audio']:
                    self.message_type = first_file.category
                else:
                    self.message_type = 'file'
        
        self.clean()
        super().save(*args, **kwargs)
        
        # If this is a new message, increment unread counts for all members except sender
        if is_new:
            # Get all conversation members except the sender
            members = ConversationMember.objects.filter(
                conversation=self.conversation
            ).exclude(user=self.sender)
            
            # Increment unread count for each member
            for member in members:
                member.unread_count = models.F('unread_count') + 1
                member.save()
        
        # Update conversation's last_message if this is the most recent
        if not self.conversation.last_message or self.created_at > self.conversation.last_message.created_at:
            self.conversation.last_message = self
            self.conversation.save()

    def update_status(self, new_status):
        """Update message status and handle related actions"""
        if new_status not in dict(self.STATUS_CHOICES):
            raise ValueError(f'Invalid status: {new_status}')
        
        self.status = new_status
        self.save()
        
        # Update conversation's last_message if this is the most recent
        if not self.conversation.last_message or self.created_at > self.conversation.last_message.created_at:
            self.conversation.last_message = self
            self.conversation.save()

    def __str__(self):
        if self.message_type == 'text':
            return f"{self.sender.username}: {self.content[:50]}..."
        elif self.message_type == 'mixed':
            return f"{self.sender.username}: {self.content[:30]}... + {self.files.count()} files"
        return f"{self.sender.username}: {self.message_type} message with {self.files.count()} files"

class MessageReaction(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    emoji = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['message', 'user', 'emoji']
        indexes = [
            models.Index(fields=['message', 'emoji']),
        ]

    def __str__(self):
        return f"{self.user.username} reacted with {self.emoji}"

class MessageThread(models.Model):
    parent_message = models.OneToOneField(Message, on_delete=models.CASCADE, related_name='threads')
    participants = models.ManyToManyField(User, related_name='threads')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_threads')
    last_reply_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-last_reply_at']
        indexes = [
            models.Index(fields=['parent_message', 'last_reply_at']),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        # Only check conversation type if parent_message is set
        if hasattr(self, 'parent_message') and self.parent_message:
            # Ensure parent message is in a group conversation
            if self.parent_message.conversation.type == 'direct':
                raise ValidationError('Threads can only be created in group conversations')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def add_participant(self, user):
        """Add a participant to the thread if they're a member of the conversation"""
        if user in self.parent_message.conversation.members.all():
            self.participants.add(user)
            return True
        return False

    def __str__(self):
        return f"Thread on {self.parent_message}"

class MessageEffect(models.Model):
    EFFECT_TYPES = [
        ('confetti', 'Confetti'),
        ('hearts', 'Hearts'),
        ('fireworks', 'Fireworks')
    ]
    
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='effects')
    effect_type = models.CharField(max_length=20, choices=EFFECT_TYPES)
    intensity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['message', 'effect_type']),
        ]
    
    def __str__(self):
        return f"{self.effect_type} effect on message {self.message.id}"

class LinkPreview(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='link_previews')
    url = models.URLField()
    title = models.CharField(max_length=255)
    description = models.TextField()
    image_url = models.URLField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['message']),
            models.Index(fields=['url']),
        ]
    
    def clean(self):
        from django.core.exceptions import ValidationError
        
        # Validate URL format
        if not self.url.startswith(('http://', 'https://')):
            raise ValidationError('URL must start with http:// or https://')
        
        # Validate title length
        if len(self.title) > 255:
            raise ValidationError('Title cannot exceed 255 characters')
        
        # Validate description length (optional)
        if self.description and len(self.description) > 1000:
            raise ValidationError('Description cannot exceed 1000 characters')
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Link preview for {self.url} in message {self.message.id}"
