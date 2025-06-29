from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db.models import Q
from .models import Connection, ConnectionRequest, UserSuggestion
from .services import calculate_network_score, calculate_activity_score, generate_user_suggestions, get_batched_alchemy_scores
from connections_api.serializers import UserSuggestionSerializer
from rest_framework import status
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def discover_users(request):
    """
    Discover new users to connect with based on various factors like interests,
    mutual connections, and activity level.
    """
    try:
        # Get user's existing connections
        existing_connections = Connection.objects.filter(
            Q(user1=request.user) | Q(user2=request.user)
        ).values_list('user1_id', 'user2_id', 'connection_strength')
        
        # Get user's connections and pending requests
        user_connections = set()
        for u1, u2, _ in existing_connections:
            other_user = u2 if u1 == request.user.id else u1
            user_connections.add(other_user)
            
        # Get pending requests
        pending_requests = ConnectionRequest.objects.filter(
            (Q(sender=request.user) | Q(receiver=request.user)) & 
            Q(status='pending')
        ).values_list('sender_id', 'receiver_id')
        
        pending_users = set()
        for s, r in pending_requests:
            pending_users.add(s)
            pending_users.add(r)
        if request.user.id in pending_users:
            pending_users.remove(request.user.id)
            
        # Get rejected users
        rejected_requests = ConnectionRequest.objects.filter(
            (Q(sender=request.user) | Q(receiver=request.user)) & 
            Q(status='rejected')
        ).values_list('sender_id', 'receiver_id')
        
        rejected_users = set()
        for s, r in rejected_requests:
            rejected_users.add(s)
            rejected_users.add(r)
        if request.user.id in rejected_users:
            rejected_users.remove(request.user.id)
            
        # Combine all excluded users
        excluded_users = user_connections.union(pending_users).union(rejected_users)
        
        # Get potential users excluding connected, pending, and rejected
        potential_users = User.objects.exclude(
            id__in=excluded_users
        ).exclude(
            id=request.user.id
        ).order_by('-last_login', 'id')
        
        # Get user's interests
        user_interests = set()
        try:
            user_interests = set(interest.name for interest in request.user.interests.all())
            logger.info(f"User {request.user.id} has {len(user_interests)} interests: {user_interests}")
        except Exception as e:
            logger.warning(f"Could not get interests for user {request.user.id}: {str(e)}")
            user_interests = set()
        
        # Process each potential user
        discover_users = []
        for user in potential_users:
            try:
                # Get user's interests
                interests = set()
                try:
                    interests = set(interest.name for interest in user.interests.all())
                    logger.info(f"Potential user {user.id} has {len(interests)} interests: {interests}")
                except Exception as e:
                    logger.warning(f"Could not get interests for potential user {user.id}: {str(e)}")
                    interests = set()
                
                # Get user's connections
                user_connections = set()
                for u1, u2, _ in existing_connections:
                    if u1 == user.id:
                        user_connections.add(u2)
                    elif u2 == user.id:
                        user_connections.add(u1)
                
                # Calculate common interests
                common_interests = list(user_interests.intersection(interests))
                
                # Calculate mutual connections
                mutual_connections = len(user_connections.intersection(request.user.connections_as_user1.all().values_list('user2_id', flat=True).union(
                    request.user.connections_as_user2.all().values_list('user1_id', flat=True)
                )))
                
                # Calculate network score
                network_score = calculate_network_score(request.user, user, existing_connections)
                
                # Calculate activity score
                activity_score = calculate_activity_score(request.user, user)
                
                # Calculate final match score (weighted average)
                match_score = (
                    (len(common_interests) / max(len(user_interests), 1)) * 0.4 +  # Interest similarity
                    network_score * 0.4 +  # Network score
                    activity_score * 0.2    # Activity score
                )
                
                # Normalize score to 0-1 range
                match_score = min(max(match_score, 0), 1)
                
                # Calculate connection strength (0-100)
                connection_strength = int(match_score * 100)
                
                # Get mutual friends
                mutual_friends = User.objects.filter(
                    Q(connections_as_user1__user2=user) | Q(connections_as_user2__user1=user),
                    Q(connections_as_user1__user2=request.user) | Q(connections_as_user2__user1=request.user)
                ).values_list('username', flat=True)[:5]  # Limit to 5 mutual friends
                
                discover_users.append({
                    'id': user.id,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'username': user.username,
                    'avatar': user.avatar.url if user.avatar else None,
                    'role': getattr(user, 'role', 'AI Professional'),
                    'location': getattr(user, 'location', 'Unknown Location'),
                    'interests': [{'name': interest} for interest in interests],
                    'common_interests': common_interests,
                    'mutual_connections': mutual_connections,
                    'mutual_friends': list(mutual_friends),
                    'match_score': match_score,
                    'connection_strength': connection_strength,
                    'last_active': user.last_login.isoformat() if user.last_login else None
                })
                
            except Exception as e:
                logger.error(f"Error processing user {user.id} for discover: {str(e)}", exc_info=True)
                continue
        
        # Sort by match score
        discover_users.sort(key=lambda x: x['match_score'], reverse=True)
        
        return Response(discover_users)
        
    except Exception as e:
        logger.error(f"Error in discover_users: {str(e)}", exc_info=True)
        return Response(
            {"error": "Failed to fetch discover users"},
            status=500
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def refresh_suggestions(request):
    """
    Refresh user suggestions by regenerating them based on current user state.
    This will clear existing suggestions and generate new ones.
    """
    try:
        # Delete existing active suggestions
        UserSuggestion.objects.filter(
            user=request.user,
            is_active=True
        ).delete()
        
        # Generate new suggestions
        suggestions, total = generate_user_suggestions(request.user)
        
        logger.info(f"Refreshed suggestions for user {request.user.id}. Generated {len(suggestions)} new suggestions.")
        
        return Response({
            "message": "Suggestions refreshed successfully",
            "suggestions_generated": len(suggestions),
            "total_potential_users": total
        })
        
    except Exception as e:
        logger.error(f"Error refreshing suggestions for user {request.user.id}: {str(e)}", exc_info=True)
        return Response(
            {"error": "Failed to refresh suggestions"},
            status=500
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def alchemy_batch(request):
    """
    Given a list of candidate user IDs, return their alchy scores for the current user in a single AI call.
    POST body: {"candidate_ids": [id1, id2, ...], "purpose_text": "..."}
    """
    candidate_ids = request.data.get('candidate_ids', [])
    purpose_text = request.data.get('purpose_text', 'find the most interesting connection')
    if not candidate_ids or not isinstance(candidate_ids, list):
        return Response({"error": "candidate_ids must be a list of user IDs."}, status=status.HTTP_400_BAD_REQUEST)
    candidates = list(User.objects.filter(id__in=candidate_ids))
    if not candidates:
        return Response({"error": "No valid candidates found."}, status=status.HTTP_400_BAD_REQUEST)
    results = get_batched_alchemy_scores(request.user, candidates, purpose_text)
    # Store/update UserSuggestion objects and serialize results
    suggestions = []
    for candidate, score in results:
        suggestion, _ = UserSuggestion.objects.update_or_create(
            user=request.user,
            suggested_user=candidate,
            defaults={
                'score': score,
                'is_active': True,
            }
        )
        suggestions.append(suggestion)
    serializer = UserSuggestionSerializer(suggestions, many=True, context={'request': request})
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def alchemy_suggestions(request):
    """
    Return only alchemy (AI) friend suggestions for the current user.
    """
    suggestions = UserSuggestion.objects.filter(user=request.user, is_active=True)
    # Use the serializer's logic for is_alchy
    serializer = UserSuggestionSerializer(suggestions, many=True, context={'request': request})
    # Filter for is_alchy in the serialized data
    alchy = [s for s in serializer.data if s.get('is_alchy')]
    return Response(alchy)
