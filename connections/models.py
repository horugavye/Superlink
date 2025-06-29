from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Q

class Connection(models.Model):
    user1 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='connections_as_user1')
    user2 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='connections_as_user2')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    connection_strength = models.IntegerField(default=0)  # 0-100 score
    match_score = models.FloatField(default=0.0)  # AI-generated match score
    last_interaction = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)  # Use this instead of status to track active/inactive connections
    mutual_connections_count = models.IntegerField(default=0)
    common_interests = models.JSONField(default=list, blank=True)

    class Meta:
        unique_together = ('user1', 'user2')
        ordering = ['-created_at']

    def __str__(self):
        return f"Connection between {self.user1.username} and {self.user2.username}"

    def deactivate(self):
        """Deactivate a connection (soft delete)"""
        self.is_active = False
        self.save()

    def reactivate(self):
        """Reactivate a connection"""
        self.is_active = True
        self.save()

class ConnectionRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),      # Initial state when request is created
        ('accepted', 'Accepted'),    # Request accepted, connection created
        ('rejected', 'Rejected'),    # Request rejected by receiver
        ('canceled', 'Canceled'),    # Request canceled by sender
    ]

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_requests')
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_requests')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    mutual_connections = models.IntegerField(default=0)
    match_score = models.FloatField(default=0.0)  # AI-generated match score
    connection_strength = models.FloatField(default=0.0)  # AI-generated connection strength
    common_interests = models.JSONField(default=list, blank=True)
    match_highlights = models.JSONField(default=list, blank=True)  # AI-generated conversation starters

    class Meta:
        unique_together = ('sender', 'receiver')
        ordering = ['-created_at']

    def __str__(self):
        return f"Connection request from {self.sender.username} to {self.receiver.username}"

    def accept(self):
        """Accept the connection request and create a new connection"""
        if self.status != 'pending':
            raise ValueError("Only pending requests can be accepted")
            
        # Create a new connection with proper score transfer
        connection = Connection.objects.create(
            user1=self.sender,
            user2=self.receiver,
            connection_strength=self.connection_strength,  # Use the exact connection_strength
            match_score=self.match_score,  # Use the exact match_score
            mutual_connections_count=self.mutual_connections,
            common_interests=self.common_interests,
            is_active=True  # Explicitly set is_active to True
        )

        # Update the request status to accepted instead of deleting
        self.status = 'accepted'
        self.save()
        
        return connection

    def reject(self):
        """Reject the connection request"""
        if self.status != 'pending':
            raise ValueError("Only pending requests can be rejected")
            
        # Mark the request as rejected first
        self.status = 'rejected'
        self.save()

        # Mark as rejected in suggestions system
        from .services import mark_user_as_rejected
        
        # Mark rejected in both directions to ensure mutual exclusion
        mark_user_as_rejected(self.receiver, self.sender)  # Receiver rejects sender
        mark_user_as_rejected(self.sender, self.receiver)  # Also mark sender's suggestion of receiver as rejected

        # Update any existing suggestions to be rejected
        UserSuggestion.objects.filter(
            (Q(user=self.sender, suggested_user=self.receiver) |
             Q(user=self.receiver, suggested_user=self.sender))
        ).update(
            is_active=False,
            is_rejected=True,
            rejected_at=timezone.now()
        )

    def cancel(self):
        """Cancel the connection request (by sender)"""
        if self.status != 'pending':
            raise ValueError("Only pending requests can be canceled")
            
        # Delete the request
        self.delete()

class UserSuggestion(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='suggestions')
    suggested_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='suggested_to')
    score = models.FloatField(default=0.0)  # AI-generated match score
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    match_highlights = models.JSONField(default=list, blank=True)  # AI-generated conversation starters
    common_interests = models.JSONField(default=list, blank=True)
    mutual_connections = models.IntegerField(default=0)
    strong_connections = models.IntegerField(default=0)  # Number of mutual connections with strength >= 75%
    is_active = models.BooleanField(default=True)
    is_rejected = models.BooleanField(default=False)  # Track if user was rejected
    rejected_at = models.DateTimeField(null=True, blank=True)  # When the user was rejected

    class Meta:
        unique_together = ('user', 'suggested_user')
        ordering = ['-score']

    def __str__(self):
        return f"Suggestion for {self.user.username}: {self.suggested_user.username}"
