from django.shortcuts import render
from rest_framework import viewsets, status, filters, permissions, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, OR
from django.shortcuts import get_object_or_404
from django.db.models import Q, F, Count, Avg
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from users.models import User
import json
import logging
from rest_framework import serializers
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from itertools import chain
from operator import attrgetter
from rest_framework.pagination import PageNumberPagination
from django.core.paginator import Paginator
from django.http import Http404
from django.core.exceptions import PermissionDenied
from rest_framework.views import APIView
from connections.models import Connection

from community.models import (
    Community, Topic, CommunityMember, PersonalPost, CommunityPost,
    PostMedia, Comment, PostRating, Event, EventParticipant,
    Reply, CommentRating, ReplyRating, SavedPost
)
from notifications.models import Notification
from .serializers import (
    CommunitySerializer, TopicSerializer, CommunityMemberSerializer,
    PostSerializer, PostMediaSerializer, CommentSerializer,
    PostRatingSerializer, EventSerializer, EventParticipantSerializer,
    ReplySerializer, CommentRatingSerializer, ReplyRatingSerializer,
    SavedPostSerializer
)
from .permissions import (
    IsCommunityMember, IsCommunityAdmin, IsCommunityModerator,
    IsPostAuthor, IsCommentAuthor, IsEventCreator, CanManageEvent,
    IsReplyAuthor
)

logger = logging.getLogger(__name__)
class TrendingTopicsView(APIView):
    """Standalone view for trending topics."""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        """Get trending topics based on post activity and engagement."""
        from django.utils import timezone
        from datetime import timedelta
        
        # Get the last 7 days for trending calculation
        week_ago = timezone.now() - timedelta(days=7)
        
        # First, try to get topics with posts (trending topics)
        trending_topics = Topic.objects.annotate(
            post_count=Count('personalpost_posts') + Count('communitypost_posts'),
            recent_post_count=Count(
                'personalpost_posts',
                filter=Q(personalpost_posts__created_at__gte=week_ago)
            ) + Count(
                'communitypost_posts',
                filter=Q(communitypost_posts__created_at__gte=week_ago)
            ),
            total_ratings=Count(
                'personalpost_posts__ratings'
            ) + Count(
                'communitypost_posts__ratings'
            ),
            total_comments=Count(
                'personalpost_posts__comments'
            ) + Count(
                'communitypost_posts__comments'
            )
        ).filter(
            post_count__gt=0  # Only include topics that have posts
        ).order_by(
            '-recent_post_count',  # Most recent activity first
            '-total_ratings',      # Then by engagement
            '-total_comments'
        )[:10]  # Limit to top 10 trending topics
        
        trending_data = []
        
        # If we have trending topics with posts, use them
        if trending_topics.exists():
            for topic in trending_topics:
                # Calculate trend percentage (recent activity vs total activity)
                if topic.post_count > 0:
                    trend_percentage = min(100, int((topic.recent_post_count / topic.post_count) * 100))
                else:
                    trend_percentage = 0
                 
                # Determine category based on community
                category = 'general'
                if topic.community:
                    category = topic.community.category
                
                trending_data.append({
                    'id': str(topic.id),
                    'name': topic.name,
                    'posts': topic.post_count,
                    'category': category,
                    'trend': trend_percentage,
                    'color': topic.color,
                    'community_name': topic.community.name if topic.community else None
                })
        else:
            # Fallback: Show popular topics from communities even without posts
            # Get topics from communities, ordered by community member count
            fallback_topics = Topic.objects.filter(
                community__isnull=False
            ).select_related('community').annotate(
                community_member_count=Count('community__members')
            ).order_by(
                '-community_member_count',
                'name'
            )[:10]
            
            for topic in fallback_topics:
                # Generate a mock trend percentage based on community popularity
                member_count = topic.community_member_count
                trend_percentage = min(100, max(10, member_count * 5))  # 10-100% based on member count
                
                trending_data.append({
                    'id': str(topic.id),
                    'name': topic.name,
                    'posts': 0,  # No posts yet
                    'category': topic.community.category if topic.community else 'general',
                    'trend': trend_percentage,
                    'color': topic.color,
                    'community_name': topic.community.name if topic.community else None
                })
        
        return Response(trending_data)

class CommunityViewSet(viewsets.ModelViewSet):
    queryset = Community.objects.all()
    serializer_class = CommunitySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    lookup_field = 'slug'

    def get_permissions(self):
        if self.action in ['update', 'partial_update']:
            return [IsAuthenticated(), IsCommunityAdmin()]
        return super().get_permissions()

    def get_queryset(self):
        queryset = Community.objects.annotate(
            active_members=Count('members', filter=Q(members__is_active=True))
        )
        return queryset

    @action(detail=False, methods=['get'])
    def user(self, request):
        """Get all communities where the user has a role"""
        communities = Community.objects.filter(
            members__user=request.user
        ).annotate(
            active_members=Count('members', filter=Q(members__is_active=True))
        )
        serializer = self.get_serializer(communities, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def discover(self, request):
        """Return all public communities the user is not a member of."""
        communities = Community.objects.exclude(
            members__user=request.user
        ).filter(is_private=False).annotate(
            active_members=Count('members', filter=Q(members__is_active=True))
        )
        serializer = self.get_serializer(communities, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def trending_topics(self, request):
        """Get trending topics based on post activity and engagement."""
        from django.utils import timezone
        from datetime import timedelta
        
        # Get the last 7 days for trending calculation
        week_ago = timezone.now() - timedelta(days=7)
        
        # Get topics with their post counts and engagement metrics
        trending_topics = Topic.objects.annotate(
            post_count=Count('personalpost_posts') + Count('communitypost_posts'),
            recent_post_count=Count(
                'personalpost_posts',
                filter=Q(personalpost_posts__created_at__gte=week_ago)
            ) + Count(
                'communitypost_posts',
                filter=Q(communitypost_posts__created_at__gte=week_ago)
            ),
            total_ratings=Count(
                'personalpost_posts__ratings'
            ) + Count(
                'communitypost_posts__ratings'
            ),
            total_comments=Count(
                'personalpost_posts__comments'
            ) + Count(
                'communitypost_posts__comments'
            )
        ).filter(
            post_count__gt=0  # Only include topics that have posts
        ).order_by(
            '-recent_post_count',  # Most recent activity first
            '-total_ratings',      # Then by engagement
            '-total_comments'
        )[:10]  # Limit to top 10 trending topics
        
        # Calculate trend percentage based on recent vs total activity
        trending_data = []
        for topic in trending_topics:
            # Calculate trend percentage (recent activity vs total activity)
            if topic.post_count > 0:
                trend_percentage = min(100, int((topic.recent_post_count / topic.post_count) * 100))
            else:
                trend_percentage = 0
            
            # Determine category based on community
            category = 'general'
            if topic.community:
                category = topic.community.category
            
            trending_data.append({
                'id': str(topic.id),
                'name': topic.name,
                'posts': topic.post_count,
                'category': category,
                'trend': trend_percentage,
                'color': topic.color,
                'community_name': topic.community.name if topic.community else None
            })
        
        return Response(trending_data)

    def perform_create(self, serializer):
        community = serializer.save()
        # Add creator as admin
        CommunityMember.objects.create(
            community=community,
            user=self.request.user,
            role='admin'
        )

    @action(detail=True, methods=['post'])
    def invite(self, request, slug=None):
        """Invite a user to join the community"""
        community = self.get_object()
        user_id = request.data.get('user_id')
        role = request.data.get('role', 'member')  # Default to member if not specified
        
        if not user_id:
            return Response(
                {'error': 'user_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate role
        if role not in ['admin', 'moderator', 'member']:
            return Response(
                {'error': 'Invalid role'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if the inviter has permission to invite
        inviter_member = get_object_or_404(
            CommunityMember,
            community=community,
            user=request.user
        )
        
        if inviter_member.role not in ['admin', 'moderator']:
            return Response(
                {'error': 'You do not have permission to invite members'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Only admins can invite as admin
        if role == 'admin' and inviter_member.role != 'admin':
            return Response(
                {'error': 'Only admins can invite other admins'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if user is already a member
        if CommunityMember.objects.filter(
            community=community,
            user_id=user_id
        ).exists():
            return Response(
                {'error': 'User is already a member'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create notification for the invitee
        Notification.objects.create(
            recipient_id=user_id,
            sender=request.user,
            notification_type='community_invite',
            title=f'Invitation to {community.name}',
            message=f'{request.user.get_full_name()} invited you to join {community.name} as {role}',
            content_type=ContentType.objects.get_for_model(community),
            object_id=community.id,
            data={
                'community_type': 'private' if community.is_private else 'public',
                'community_id': community.id,
                'community_slug': community.slug,
                'community_name': community.name,
                'inviter_name': request.user.get_full_name(),
                'role': role  # Include the role in the notification data
            }
        )

        return Response(
            {'message': 'Invitation sent successfully'},
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['post'])
    def invite_bulk(self, request, slug=None):
        """Invite multiple users to join the community"""
        logger.info(f'[Backend] Received bulk invite request for community: {slug}')
        logger.info(f'[Backend] Request data: {request.data}')
        
        community = self.get_object()
        recipients = request.data.get('recipients', [])
        template = request.data.get('template', 'default')
        
        if not recipients:
            logger.warning('[Backend] No recipients provided in request')
            return Response(
                {'error': 'No recipients provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if the inviter has permission to invite
        try:
            inviter_member = get_object_or_404(
                CommunityMember,
                community=community,
                user=request.user
            )
            
            if inviter_member.role not in ['admin', 'moderator']:
                logger.warning(f'[Backend] User {request.user.id} does not have permission to invite members')
                return Response(
                    {'error': 'You do not have permission to invite members'},
                    status=status.HTTP_403_FORBIDDEN
                )
        except Exception as e:
            logger.error(f'[Backend] Error checking inviter permissions: {str(e)}')
            return Response(
                {'error': 'Error checking permissions'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        successful_invites = []
        failed_invites = []

        for recipient in recipients:
            email = recipient.get('email')
            role = recipient.get('role', 'member')
            message = recipient.get('message', '')

            logger.info(f'[Backend] Processing invite for email: {email}')

            if not email:
                logger.warning('[Backend] Missing email in recipient data')
                failed_invites.append({'email': email, 'error': 'Email is required'})
                continue

            # Check if user exists with this email
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                logger.warning(f'[Backend] User not found for email: {email}')
                failed_invites.append({'email': email, 'error': 'User not found'})
                continue

            # Check if user is already a member
            if CommunityMember.objects.filter(
                community=community,
                user=user
            ).exists():
                logger.warning(f'[Backend] User {user.id} is already a member of community {community.id}')
                failed_invites.append({'email': email, 'error': 'User is already a member'})
                continue

            try:
                # Create notification for the invitee
                Notification.objects.create(
                    recipient=user,
                    sender=request.user,
                    notification_type='community_invite',
                    title=f'Invitation to {community.name}',
                    message=message or f'{request.user.get_full_name()} invited you to join {community.name}',
                    content_type=ContentType.objects.get_for_model(community),
                    object_id=community.id,
                    data={
                        'community_type': 'private' if community.is_private else 'public',
                        'community_id': community.id,
                        'community_slug': community.slug,
                        'community_name': community.name,
                        'inviter_name': request.user.get_full_name(),
                        'role': role
                    }
                )
                logger.info(f'[Backend] Successfully created invite notification for user {user.id}')
                successful_invites.append({'email': email})
            except Exception as e:
                logger.error(f'[Backend] Error creating notification for user {user.id}: {str(e)}')
                failed_invites.append({'email': email, 'error': 'Failed to create notification'})

        logger.info(f'[Backend] Bulk invite completed. Successful: {len(successful_invites)}, Failed: {len(failed_invites)}')
        return Response({
            'message': f'Successfully sent {len(successful_invites)} invitations',
            'successful_invites': successful_invites,
            'failed_invites': failed_invites
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def join(self, request, slug=None):
        """Join a community, handling both direct joins and invitation acceptance"""
        community = self.get_object()
        logger.info(f'[Backend] Join request received for community: {slug}')
        logger.info(f'[Backend] Request data: {request.data}')
        
        # Check if this is an invitation acceptance
        notification_id = request.data.get('notification_id')
        if notification_id:
            try:
                logger.info(f'[Backend] Processing invitation acceptance for notification: {notification_id}')
                notification = Notification.objects.get(
                    id=notification_id,
                    recipient=request.user,
                    notification_type='community_invite',
                    content_type=ContentType.objects.get_for_model(community),
                    object_id=community.id
                )
                # Get the role from the notification data
                role = notification.data.get('role', 'member')
                logger.info(f'[Backend] Retrieved role from notification data: {role}')
                logger.info(f'[Backend] Full notification data: {notification.data}')
                notification.delete()  # Remove the notification after accepting
            except Notification.DoesNotExist:
                logger.error(f'[Backend] Invalid or expired invitation for notification: {notification_id}')
                return Response(
                    {'error': 'Invalid or expired invitation'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            # Direct join attempt
            if community.is_private:
                logger.warning(f'[Backend] Direct join attempt for private community: {slug}')
                return Response(
                    {'error': 'This community is private'},
                    status=status.HTTP_403_FORBIDDEN
                )
            role = 'member'  # Default role for direct joins
            logger.info(f'[Backend] Direct join with default role: {role}')
        
        # Create the membership with the specified role
        logger.info(f'[Backend] Creating membership with role: {role}')
        member, created = CommunityMember.objects.get_or_create(
            community=community,
            user=request.user,
            defaults={'role': role}
        )
        
        if not created:
            logger.warning(f'[Backend] User already a member of community: {slug}')
            return Response(
                {'error': 'Already a member'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        logger.info(f'[Backend] Successfully joined community as {role}')
        return Response(
            {'message': f'Successfully joined community as {role}'},
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'])
    def leave(self, request, slug=None):
        community = self.get_object()
        member = get_object_or_404(
            CommunityMember,
            community=community,
            user=request.user
        )
        
        # If the member is an admin, check if there are other admins
        if member.role == 'admin':
            admin_count = CommunityMember.objects.filter(
                community=community,
                role='admin'
            ).count()
            
            if admin_count <= 1:
                return Response(
                    {'error': 'Cannot leave as the last admin. Please transfer admin rights first.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        member.delete()
        return Response(
            {'message': 'Successfully left community'},
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['delete'])
    def delete_community(self, request, slug=None):
        """Delete a community (admin only)"""
        community = self.get_object()
        
        # Check if the user is an admin of the community
        member = get_object_or_404(
            CommunityMember,
            community=community,
            user=request.user
        )
        
        if member.role != 'admin':
            return Response(
                {'error': 'Only admins can delete the community'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Delete the community
        community.delete()
        return Response(
            {'message': 'Community successfully deleted'},
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'])
    def change_role(self, request, slug=None):
        """Change a member's role in the community"""
        community = self.get_object()
        user_id = request.data.get('user_id')
        new_role = request.data.get('role')

        if not user_id or not new_role:
            return Response(
                {'error': 'user_id and role are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if new_role not in ['admin', 'moderator', 'member']:
            return Response(
                {'error': 'Invalid role'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if the requester has permission to change roles
        requester_member = get_object_or_404(
            CommunityMember,
            community=community,
            user=request.user
        )
        
        if requester_member.role != 'admin':
            return Response(
                {'error': 'Only admins can change roles'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get the member to update
        member_to_update = get_object_or_404(
            CommunityMember,
            community=community,
            user_id=user_id
        )

        # Prevent changing the last admin's role
        if member_to_update.role == 'admin' and new_role != 'admin':
            admin_count = CommunityMember.objects.filter(
                community=community,
                role='admin'
            ).count()
            if admin_count <= 1:
                return Response(
                    {'error': 'Cannot remove the last admin'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Update the role
        member_to_update.role = new_role
        member_to_update.save()

        return Response(
            {'message': f'Successfully updated role to {new_role}'},
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'])
    def add_member(self, request, slug=None):
        """Directly add a member to the community"""
        community = self.get_object()
        user_id = request.data.get('user_id')
        role = request.data.get('role', 'member')  # Default to member if not specified
        
        if not user_id:
            return Response(
                {'error': 'user_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate role
        if role not in ['admin', 'moderator', 'member']:
            return Response(
                {'error': 'Invalid role'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if the adder has permission to add members
        adder_member = get_object_or_404(
            CommunityMember,
            community=community,
            user=request.user
        )
        
        if adder_member.role not in ['admin', 'moderator']:
            return Response(
                {'error': 'You do not have permission to add members'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Only admins can add as admin
        if role == 'admin' and adder_member.role != 'admin':
            return Response(
                {'error': 'Only admins can add other admins'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if user is already a member
        if CommunityMember.objects.filter(
            community=community,
            user_id=user_id
        ).exists():
            return Response(
                {'error': 'User is already a member'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Add the member directly
        member = CommunityMember.objects.create(
            community=community,
            user_id=user_id,
            role=role
        )

        return Response(
            {'message': f'Successfully added member with role: {role}'},
            status=status.HTTP_200_OK
        )

class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer
    permission_classes = [IsAuthenticated, IsCommunityModerator]

class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'content', 'topics__name']
    ordering_fields = ['created_at', 'rating', 'view_count', 'comment_count']
    ordering = ['-is_pinned', '-created_at']

    def get_queryset(self):
        # Return all community posts for detail endpoints
        return CommunityPost.objects.select_related('author', 'community').prefetch_related('topics')

    def retrieve(self, request, *args, **kwargs):
        """Retrieve a single post (either personal or community)"""
        post_id = self.kwargs.get('pk')
        community_slug = self.kwargs.get('community_slug')
        if not post_id:
            return Response({'error': 'Post ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        # If community_slug is present, fetch CommunityPost by both pk and community__slug
        if community_slug:
            try:
                post = CommunityPost.objects.select_related('author', 'community').prefetch_related('topics').get(pk=post_id, community__slug=community_slug)
            except CommunityPost.DoesNotExist:
                return Response({'error': 'Community post not found for this community'}, status=status.HTTP_404_NOT_FOUND)
        else:
            # Try to get the post from either model
            try:
                # First try to get a personal post
                post = PersonalPost.objects.select_related('author').prefetch_related('topics').get(pk=post_id)
            except PersonalPost.DoesNotExist:
                try:
                    # If not found, try to get a community post (fallback, should not happen for personal route)
                    post = CommunityPost.objects.select_related('author', 'community').prefetch_related('topics').get(pk=post_id)
                except CommunityPost.DoesNotExist:
                    return Response({'error': 'Post not found'}, status=status.HTTP_404_NOT_FOUND)

        # Check permissions for private posts
        if hasattr(post, 'community') and post.community and post.community.is_private:
            if not request.user.is_authenticated:
                return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
            
            # Check if user is a member of the private community
            if not post.community.members.filter(user=request.user, is_active=True).exists():
                return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(post)
        return Response(serializer.data)

    def get_object(self):
        community_slug = self.kwargs.get('community_slug')
        pk = self.kwargs.get('pk')
        if community_slug:
            # Fetch CommunityPost for this community
            return CommunityPost.objects.get(pk=pk, community__slug=community_slug)
        else:
            # Fallback to PersonalPost
            return PersonalPost.objects.get(pk=pk)

    def list(self, request, *args, **kwargs):
        personal_posts = PersonalPost.objects.select_related('author').prefetch_related('topics')
        community_posts = CommunityPost.objects.select_related('author', 'community').prefetch_related('topics')

        # Filter by community if specified
        community_slug = self.request.query_params.get('community')
        if community_slug:
            community_posts = community_posts.filter(community__slug=community_slug)

        # Filter by visibility if specified
        visibility = self.request.query_params.get('visibility')
        if visibility:
            personal_posts = personal_posts.filter(visibility=visibility)
            community_posts = community_posts.filter(visibility=visibility)

        user = self.request.user
        if not user.is_authenticated:
            # Unauthenticated users: only see public personal posts and public community posts
            personal_posts = personal_posts.filter(visibility='personal_public')
            community_posts = community_posts.filter(community__is_private=False)
        else:
            # Authenticated users: build connection user IDs set
            connection_ids = set(Connection.objects.filter(
                (Q(user1=user) | Q(user2=user)),
                is_active=True
            ).values_list('user1_id', 'user2_id'))
            # Flatten connection IDs and remove self
            flat_ids = set()
            for u1, u2 in connection_ids:
                flat_ids.add(u1)
                flat_ids.add(u2)
            flat_ids.discard(user.id)
            # Personal posts: show
            # - own posts (any visibility)
            # - connections' posts with 'personal_connections' visibility
            # - anyone's posts with 'personal_public' visibility
            personal_posts = personal_posts.filter(
                Q(author=user) |
                Q(visibility='personal_connections', author__id__in=flat_ids) |
                Q(visibility='personal_public')
            )
            # Community posts: show
            # - public communities (always)
            # - private communities only if user is a member
            community_posts = community_posts.filter(
                Q(community__is_private=False) |
                Q(community__is_private=True, community__members__user=user)
            ).distinct()

        # For personal feed, show:
        # 1. User's personal posts
        # 2. Posts from user's communities
        if self.request.query_params.get('feed') == 'personal':
            user_communities = Community.objects.filter(members__user=user)
            personal_posts = personal_posts.filter(author=user)
            community_posts = community_posts.filter(community__in=user_communities)

        # For community feed, show posts with community visibility in the specified community
        elif community_slug:
            community_posts = community_posts.filter(community__slug=community_slug)

        # Get the post ID from the URL if it exists
        post_id = self.kwargs.get('pk')
        if post_id:
            personal_post = personal_posts.filter(pk=post_id).first()
            community_post = community_posts.filter(pk=post_id).first()

            if personal_post:
                return Response(self.get_serializer([personal_post], many=True).data)
            elif community_post:
                return Response(self.get_serializer([community_post], many=True).data)
            return Response([])

        # For list view, return both personal and community posts as a sorted list
        from itertools import chain
        from operator import attrgetter
        all_posts = sorted(
            chain(personal_posts, community_posts),
            key=attrgetter('created_at'),
            reverse=True
        )

        # Manual pagination using Django's Paginator
        page_size = int(request.query_params.get('page_size', 10))
        page_number = int(request.query_params.get('page', 1))
        paginator = Paginator(all_posts, page_size)
        page = paginator.get_page(page_number)

        serializer = self.get_serializer(page.object_list, many=True, context={'request': request})
        return Response({
            'count': paginator.count,
            'num_pages': paginator.num_pages,
            'current_page': page_number,
            'results': serializer.data
        })

    @action(detail=False, methods=['get'], url_path='feed')
    def feed(self, request):
        """Get posts for the user's feed based on the feed type"""
        feed_type = request.query_params.get('type', 'personal')
        
        # Get both personal and community posts with their related fields
        personal_posts = PersonalPost.objects.select_related('author', 'community').prefetch_related('topics')
        community_posts = CommunityPost.objects.select_related('author', 'community').prefetch_related('topics')
        
        if feed_type == 'personal':
            # For personal feed, show:
            # - own posts (any visibility)
            # - connections' posts with 'personal_connections' visibility
            # - anyone's posts with 'personal_public' visibility
            from connections.models import Connection
            from django.db.models import Q
            user = request.user
            connection_ids = set(Connection.objects.filter(
                (Q(user1=user) | Q(user2=user)),
                is_active=True
            ).values_list('user1_id', 'user2_id'))
            flat_ids = set()
            for u1, u2 in connection_ids:
                flat_ids.add(u1)
                flat_ids.add(u2)
            flat_ids.discard(user.id)
            posts = personal_posts.filter(
                Q(author=user) |
                Q(visibility='personal_connections', author__id__in=flat_ids) |
                Q(visibility='personal_public')
            )
            posts_count = posts.count()
            community_posts_count = 0
        elif feed_type == 'community':
            # For community feed, only show community posts
            posts = community_posts.filter(visibility='community')
            posts_count = 0
            community_posts_count = posts.count()
        
        # Sort posts by creation date
        posts = posts.order_by('-created_at')
        
        # Serialize the posts
        serializer = self.get_serializer(posts, many=True, context={'request': request})
        return Response({
            'posts': serializer.data,
            'counts': {
                'personal_posts': posts_count,
                'community_posts': community_posts_count,
                'total_posts': posts_count + community_posts_count
            }
        })

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsPostAuthor()]
        return super().get_permissions()

    @action(detail=False, methods=['post'], url_path='personal/posts')
    def create_personal_post(self, request):
        """Create a personal post (not associated with any community)"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Create the post with personal visibility
        post = serializer.save(
            author=request.user,
            community=None,
            visibility=request.data.get('visibility', 'personal_private')
        )
        
        # Handle media files
        media_files = request.FILES.getlist('media')
        for index, media_file in enumerate(media_files):
            media_type = 'video' if media_file.content_type.startswith('video/') else 'image'
            PostMedia.objects.create(
                personal_post=post,
                type=media_type,
                file=media_file,
                order=index
            )
        
        # Handle topics
        topics = request.data.getlist('topics')
        if topics:
            existing_topics = Topic.objects.filter(name__in=topics)
            post.topics.add(*existing_topics)
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        # Get community from request data
        community_slug = self.request.data.get('community_slug')
        visibility = self.request.data.get('visibility', 'community')  # Default to community for community posts
        
        # Get community if specified
        community = None
        if community_slug:
            community = get_object_or_404(Community, slug=community_slug)
        
        # Create the post
        post = serializer.save(
            author=self.request.user,
            community=community,
            visibility=visibility
        )
        
        # Handle media files
        media_files = self.request.FILES.getlist('media')
        for index, media_file in enumerate(media_files):
            media_type = 'video' if media_file.content_type.startswith('video/') else 'image'
            
            # Create media based on post type
            if isinstance(post, PersonalPost):
                PostMedia.objects.create(
                    personal_post=post,
                    type=media_type,
                    file=media_file,
                    order=index
                )
            else:  # CommunityPost
                PostMedia.objects.create(
                    community_post=post,
                    type=media_type,
                    file=media_file,
                    order=index
                )
        
        # Handle topics - get existing topics for the community
        topics = self.request.data.getlist('topics')
        if community and topics:
            # Only get existing topics from the community
            existing_topics = Topic.objects.filter(
                name__in=topics,
                community=community
            )
            
            # Add only the existing topics to the post
            if existing_topics.exists():
                post.topics.add(*existing_topics)
        
        # Send WebSocket notification if it's a community post
        if post.visibility == 'community' and post.community:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"community_{post.community.slug}",
                {
                    'type': 'post_created',
                    'data': {
                        'post_id': post.id,
                        'title': post.title,
                        'author': {
                            'id': post.author.id,
                            'username': post.author.username,
                            'avatar': post.author.avatar.url if post.author.avatar else None
                        },
                        'visibility': post.visibility,
                        'community': {
                            'id': post.community.id,
                            'name': post.community.name
                        }
                    }
                }
            )

    @action(detail=True, methods=['post', 'delete'])
    def rate(self, request, pk=None, community_slug=None):
        from community.models import PostRating, PersonalPost, CommunityPost
        post = self.get_object()

        # Log the type and ID of the post and user
        logger.warning(f"[RATE] post type: {type(post)}, post id: {getattr(post, 'id', None)}, user: {request.user}")

        # Handle unrating (DELETE request)
        if request.method == 'DELETE':
            if isinstance(post, PersonalPost):
                PostRating.objects.filter(personal_post=post, user=request.user).delete()
                ratings = PostRating.objects.filter(personal_post=post)
            else:  # CommunityPost
                PostRating.objects.filter(community_post=post, user=request.user).delete()
                ratings = PostRating.objects.filter(community_post=post)

            post.total_ratings = ratings.count()
            post.rating = ratings.aggregate(Avg('rating'))['rating__avg'] or 0
            post.save()

            # WebSocket update for community posts
            if isinstance(post, CommunityPost):
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"community_{community_slug}",
                    {
                        'type': 'rating_update',
                        'data': {
                            'post_id': post.id,
                            'rating': float(post.rating),
                            'total_ratings': post.total_ratings,
                            'user_rating': 0
                        }
                    }
                )

            return Response({
                'rating': float(post.rating),
                'total_ratings': post.total_ratings,
                'user_rating': 0
            })

        # Handle rating (POST request)
        rating = request.data.get('rating')
        rating = float(rating)
        if rating < 1 or rating > 5:
            return Response({'error': 'Valid rating (1-5) is required'}, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(post, PersonalPost):
            post_rating, created = PostRating.objects.get_or_create(
                personal_post=post,
                user=request.user,
                defaults={'rating': rating}
            )
        else:  # CommunityPost
            post_rating, created = PostRating.objects.get_or_create(
                community_post=post,
                user=request.user,
                defaults={'rating': rating}
            )

        # Log after get_or_create
        logger.warning(f"[RATE] PostRating created: {created}, post_rating id: {getattr(post_rating, 'id', None)}, community_post: {getattr(post_rating, 'community_post_id', None)}, personal_post: {getattr(post_rating, 'personal_post_id', None)}, user: {getattr(post_rating, 'user_id', None)}, rating: {getattr(post_rating, 'rating', None)}")

        if not created:
            post_rating.rating = rating
            post_rating.save()

        if isinstance(post, PersonalPost):
            ratings = PostRating.objects.filter(personal_post=post)
        else:
            ratings = PostRating.objects.filter(community_post=post)

        post.total_ratings = ratings.count()
        post.rating = ratings.aggregate(Avg('rating'))['rating__avg'] or 0
        post.save()

        # WebSocket update for community posts
        if isinstance(post, CommunityPost):
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"community_{community_slug}",
                {
                    'type': 'rating_update',
                    'data': {
                        'post_id': post.id,
                        'rating': float(post.rating),
                        'total_ratings': post.total_ratings,
                        'user_rating': float(rating)
                    }
                }
            )

        return Response({
            'rating': float(post.rating),
            'total_ratings': post.total_ratings,
            'user_rating': float(rating)
        })

    @action(detail=True, methods=['post'])
    def pin(self, request, pk=None):
        post = self.get_object()
        
        # Check if user has permission to pin posts in the post's community
        if post.visibility == 'community' and post.community:
            if not CommunityMember.objects.filter(
                community=post.community,
                user=request.user,
                role__in=['admin', 'moderator']
            ).exists():
                return Response(
                    {'error': 'You do not have permission to pin posts'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        post.is_pinned = not post.is_pinned
        post.save()
        
        # Send WebSocket update if it's a community post
        if post.visibility == 'community' and post.community:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"community_{post.community.slug}",
                {
                    'type': 'post_pinned',
                    'data': {
                        'post_id': post.id,
                        'is_pinned': post.is_pinned
                    }
                }
            )
        
        return Response({
            'is_pinned': post.is_pinned
        })

class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        post_id = self.kwargs.get('post_pk')
        if not post_id:
            return Comment.objects.none()

        # Try to get the post from either model
        try:
            post = CommunityPost.objects.get(pk=post_id)
            return Comment.objects.filter(community_post=post)
        except CommunityPost.DoesNotExist:
            try:
                post = PersonalPost.objects.get(pk=post_id)
                return Comment.objects.filter(personal_post=post)
            except PersonalPost.DoesNotExist:
                return Comment.objects.none()

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), OR(IsCommentAuthor(), IsCommunityModerator())]
        return super().get_permissions()

    def perform_create(self, serializer):
        post_id = self.kwargs.get('post_pk')
        if not post_id:
            raise serializers.ValidationError("Post ID is required")

        # Try to get the post from either model
        try:
            post = CommunityPost.objects.get(pk=post_id)
            serializer.save(author=self.request.user, community_post=post)
        except CommunityPost.DoesNotExist:
            try:
                post = PersonalPost.objects.get(pk=post_id)
                serializer.save(author=self.request.user, personal_post=post)
            except PersonalPost.DoesNotExist:
                raise serializers.ValidationError("Post not found")

    @action(detail=True, methods=['post'])
    def rate(self, request, pk=None, comment_pk=None, post_pk=None, community_slug=None):
        try:
            comment = self.get_object()
            rating_value = request.data.get('rating')
            
            # Handle unrating (rating = 0)
            if rating_value == 0:
                # Delete the rating if it exists
                CommentRating.objects.filter(comment=comment, user=request.user).delete()
                
                # The signal will handle updating comment rating and total ratings
                comment.refresh_from_db()
                
                return Response({
                    'rating': float(comment.rating),
                    'total_ratings': comment.total_ratings,
                    'user_rating': 0,
                    'comment': CommentSerializer(comment, context={'request': request}).data
                })
            
            # Handle normal rating (1-5)
            if not rating_value or not isinstance(rating_value, (int, float)) or rating_value < 1 or rating_value > 5:
                return Response({'detail': 'Invalid rating value'}, status=status.HTTP_400_BAD_REQUEST)

            rating, created = CommentRating.objects.update_or_create(
                comment=comment,
                user=request.user,
                defaults={'rating': rating_value}
            )

            # The signal will handle updating comment rating and total ratings
            comment.refresh_from_db()
            
            # Send WebSocket update if it's a community post
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
                            'user_rating': float(rating_value)
                        }
                    }
                )
            
            return Response({
                'rating': float(comment.rating),
                'total_ratings': comment.total_ratings,
                'user_rating': float(rating_value),
                'comment': CommentSerializer(comment, context={'request': request}).data
            })
        except Exception as e:
            logger.error(f"Error in comment rating: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def mark_top(self, request, pk=None, post_pk=None):
        comment = self.get_object()
        post = comment.personal_post or comment.community_post
        
        if not request.user.is_staff and not (isinstance(post, CommunityPost) and post.community.members.filter(
            user=request.user, role__in=['admin', 'moderator']
        ).exists()):
            return Response({'detail': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
        
        # Unmark any existing top comments
        Comment.objects.filter(
            Q(personal_post=post) | Q(community_post=post),
            is_top_comment=True
        ).update(is_top_comment=False)
        
        comment.is_top_comment = True
        comment.save()
        return Response(self.get_serializer(comment).data)

class ReplyViewSet(viewsets.ModelViewSet):
    serializer_class = ReplySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at']
    ordering = ['created_at']
    lookup_field = 'pk'

    def get_queryset(self):
        return Reply.objects.filter(comment_id=self.kwargs['comment_pk'])

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), OR(IsReplyAuthor(), IsCommunityModerator())]
        return super().get_permissions()

    def perform_create(self, serializer):
        comment = get_object_or_404(Comment, pk=self.kwargs['comment_pk'])
        parent_reply_id = self.request.data.get('parent_reply')
        if parent_reply_id:
            parent_reply = get_object_or_404(Reply, pk=parent_reply_id)
            serializer.save(author=self.request.user, comment=comment, parent_reply=parent_reply)
        else:
            serializer.save(author=self.request.user, comment=comment)

    def destroy(self, request, *args, **kwargs):
        try:
            reply = self.get_object()
            # Store necessary information before deletion
            post = reply.comment.personal_post or reply.comment.community_post
            post_id = post.id
            comment_id = reply.comment.id
            reply_id = reply.id
            community_slug = post.community.slug if isinstance(post, CommunityPost) else None

            # Delete the reply
            self.perform_destroy(reply)

            # Send WebSocket update if it's a community post
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

            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.error(f"Error deleting reply: {str(e)}")
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def rate(self, request, pk=None, comment_pk=None, post_pk=None, community_slug=None):
        try:
            reply = self.get_object()
            rating_value = request.data.get('rating')
            
            # Handle unrating (rating = 0)
            if rating_value == 0:
                # Delete the rating if it exists
                ReplyRating.objects.filter(reply=reply, user=request.user).delete()
                
                # The signal will handle updating reply rating and total ratings
                reply.refresh_from_db()
                
                return Response({
                    'rating': float(reply.rating),
                    'total_ratings': reply.total_ratings,
                    'user_rating': 0,
                    'reply': ReplySerializer(reply, context={'request': request}).data
                })
            
            # Handle normal rating (1-5)
            if not rating_value or not isinstance(rating_value, (int, float)) or rating_value < 1 or rating_value > 5:
                return Response({'detail': 'Invalid rating value'}, status=status.HTTP_400_BAD_REQUEST)

            rating, created = ReplyRating.objects.update_or_create(
                reply=reply,
                user=request.user,
                defaults={'rating': rating_value}
            )

            # The signal will handle updating reply rating and total ratings
            reply.refresh_from_db()
            
            # Send WebSocket update if it's a community post
            post = reply.comment.personal_post or reply.comment.community_post
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
                            'user_rating': float(rating_value)
                        }
                    }
                )
            
            return Response({
                'rating': float(reply.rating),
                'total_ratings': reply.total_ratings,
                'user_rating': float(rating_value),
                'reply': ReplySerializer(reply, context={'request': request}).data
            })
        except Exception as e:
            logger.error(f"Error in reply rating: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description']
    ordering_fields = ['start_date', 'participants_count']
    ordering = ['-start_date']

    def get_queryset(self):
        queryset = Event.objects.all()
        community_id = self.request.query_params.get('community', None)
        if community_id:
            queryset = queryset.filter(community_id=community_id)
        return queryset

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), CanManageEvent()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def join(self, request, pk=None):
        event = self.get_object()
        if event.participants.filter(user=request.user).exists():
            return Response({'detail': 'Already participating'}, status=status.HTTP_400_BAD_REQUEST)
        
        if event.max_participants and event.participants_count >= event.max_participants:
            return Response({'detail': 'Event is full'}, status=status.HTTP_400_BAD_REQUEST)
        
        participant = EventParticipant.objects.create(
            event=event,
            user=request.user
        )
        event.participants_count = F('participants_count') + 1
        event.save()
        return Response(EventParticipantSerializer(participant).data)

    @action(detail=True, methods=['post'])
    def leave(self, request, pk=None):
        event = self.get_object()
        participant = event.participants.filter(user=request.user).first()
        if not participant:
            return Response({'detail': 'Not participating'}, status=status.HTTP_400_BAD_REQUEST)
        
        participant.delete()
        event.participants_count = F('participants_count') - 1
        event.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'])
    def participants(self, request, pk=None):
        event = self.get_object()
        participants = event.participants.all()
        serializer = EventParticipantSerializer(participants, many=True)
        return Response(serializer.data)

class CommunityMembersListView(generics.ListAPIView):
    serializer_class = CommunityMemberSerializer

    def get_queryset(self):
        slug = self.kwargs['slug']
        return CommunityMember.objects.filter(community__slug=slug)

class CommunityMemberDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = CommunityMemberSerializer
    lookup_field = 'pk'
    lookup_url_kwarg = 'pk'

    def get_queryset(self):
        slug = self.kwargs['slug']
        return CommunityMember.objects.filter(community__slug=slug)

    def destroy(self, request, *args, **kwargs):
        """Delete a member from the community"""
        slug = self.kwargs['slug']
        user_id = self.kwargs['pk']

        try:
            # Get the community
            community = Community.objects.get(slug=slug)
            
            # Get the member to delete
            member = CommunityMember.objects.get(
                community=community,
                user_id=user_id
            )

            # Check if the requester has permission to remove members
            requester_member = CommunityMember.objects.get(
                community=community,
                user=request.user
            )
            
            if requester_member.role != 'admin':
                return Response(
                    {'error': 'Only admins can remove members'},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Prevent removing yourself
            if member.user_id == request.user.id:
                return Response(
                    {'error': 'You cannot remove yourself from the community'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Prevent removing other admins
            if member.role == 'admin':
                return Response(
                    {'error': 'Admins cannot remove other admins'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Delete the member
            member.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Community.DoesNotExist:
            return Response(
                {'error': 'Community not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except CommunityMember.DoesNotExist:
            return Response(
                {'error': 'Member not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class SavedPostViewSet(viewsets.ModelViewSet):
    serializer_class = SavedPostSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SavedPost.objects.filter(user=self.request.user)

    @action(detail=False, methods=['post'])
    def save(self, request):
        post_id = request.data.get('post_id')
        is_personal = request.data.get('is_personal', False)
        if not post_id:
            return Response(
                {'error': 'Post ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            if is_personal:
                post = PersonalPost.objects.get(pk=post_id)
                saved_post, created = SavedPost.objects.get_or_create(
                    user=request.user,
                    personal_post=post
                )
            else:
                post = CommunityPost.objects.get(pk=post_id)
                saved_post, created = SavedPost.objects.get_or_create(
                    user=request.user,
                    community_post=post
                )

            if not created:
                return Response(
                    {'error': 'Post is already saved'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            serializer = self.get_serializer(saved_post)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except (PersonalPost.DoesNotExist, CommunityPost.DoesNotExist):
            return Response(
                {'error': 'Post not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def unsave(self, request):
        post_id = request.data.get('post_id')
        is_personal = request.data.get('is_personal', False)
        if not post_id:
            return Response(
                {'error': 'Post ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            if is_personal:
                saved_post = SavedPost.objects.filter(
                    user=request.user,
                    personal_post_id=post_id
                )
            else:
                saved_post = SavedPost.objects.filter(
                    user=request.user,
                    community_post_id=post_id
                )

            if not saved_post.exists():
                return Response(
                    {'error': 'Post is not saved'},
                    status=status.HTTP_404_NOT_FOUND
                )

            saved_post.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
