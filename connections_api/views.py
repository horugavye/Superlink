from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import models
from django.core.exceptions import ObjectDoesNotExist
import logging
from connections.models import Connection, ConnectionRequest, UserSuggestion
from .serializers import (
    ConnectionSerializer, ConnectionRequestSerializer, 
    UserSuggestionSerializer
)
from api.serializers import PersonalityTagSerializer, UserInterestSerializer
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

class ConnectionViewSet(viewsets.ModelViewSet):
    serializer_class = ConnectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        try:
            return Connection.objects.filter(
                models.Q(user1=self.request.user) | 
                models.Q(user2=self.request.user)
            )
        except Exception as e:
            logger.error(f"Error in ConnectionViewSet.get_queryset: {str(e)}")
            raise

    @action(detail=False, methods=['get'])
    def discover(self, request):
        """Get potential connections for the current user."""
        try:
            from django.contrib.auth import get_user_model
            from django.db.models import Q
            User = get_user_model()

            # Get users who are not already connected or have pending requests
            connected_users = Connection.objects.filter(
                Q(user1=request.user) | Q(user2=request.user)
            ).values_list('user1', 'user2')

            # Flatten the list of connected users
            connected_user_ids = set()
            for user1, user2 in connected_users:
                connected_user_ids.add(user1)
                connected_user_ids.add(user2)

            # Get users with pending requests
            pending_request_users = ConnectionRequest.objects.filter(
                Q(sender=request.user) | Q(receiver=request.user),
                status='pending'
            ).values_list('sender', 'receiver')

            # Flatten the list of users with pending requests
            pending_user_ids = set()
            for sender, receiver in pending_request_users:
                pending_user_ids.add(sender)
                pending_user_ids.add(receiver)

            # Combine all excluded users
            excluded_user_ids = connected_user_ids.union(pending_user_ids)

            # Get potential connections
            potential_users = User.objects.exclude(
                id__in=excluded_user_ids
            ).exclude(
                id=request.user.id  # Exclude current user
            ).prefetch_related(
                'interests',
                'personality_tags'
            )

            # Transform the data to match the frontend expectations
            discover_data = []
            for user in potential_users:
                try:
                    # Get personality tags
                    personality_tags = user.personality_tags.all()
                    personality_tags_data = PersonalityTagSerializer(personality_tags, many=True).data

                    # Get user's interests
                    user_interests = user.interests.all()
                    interests_data = UserInterestSerializer(user_interests, many=True).data

                    # Calculate common interests with current user
                    current_user_interests = set(request.user.interests.values_list('name', flat=True))
                    user_interests_set = set(user.interests.values_list('name', flat=True))
                    common_interests = list(current_user_interests.intersection(user_interests_set))

                    # Calculate mutual connections
                    mutual_connections = Connection.objects.filter(
                        Q(user1=user) | Q(user2=user),
                        is_active=True
                    ).filter(
                        Q(user1__in=connected_user_ids) | Q(user2__in=connected_user_ids)
                    ).count()

                    # Calculate match score and connection strength (simple example, replace with real logic)
                    def calculate_match_score(user, current_user):
                        """
                        Calculate match score based on:
                        - Common interests (40%)
                        - Role compatibility (20%)
                        - Personality tags overlap (20%)
                        - Location proximity (20%)
                        """
                        score = 0
                        
                        # Calculate interests match (40% weight)
                        current_user_interests = set(current_user.interests.values_list('name', flat=True))
                        user_interests = set(user.interests.values_list('name', flat=True))
                        
                        if current_user_interests and user_interests:
                            common_interests = len(current_user_interests.intersection(user_interests))
                            total_interests = len(current_user_interests.union(user_interests))
                            interests_score = (common_interests / total_interests if total_interests > 0 else 0) * 40
                            score += interests_score

                        # Calculate role compatibility (20% weight)
                        if user.role and current_user.role:
                            # Simple role matching - can be expanded with role compatibility matrix
                            role_score = 20 if user.role == current_user.role else 10
                            score += role_score

                        # Calculate personality tags overlap (20% weight)
                        current_user_tags = set(current_user.personality_tags.values_list('name', flat=True))
                        user_tags = set(user.personality_tags.values_list('name', flat=True))
                        
                        if current_user_tags and user_tags:
                            common_tags = len(current_user_tags.intersection(user_tags))
                            total_tags = len(current_user_tags.union(user_tags))
                            personality_score = (common_tags / total_tags if total_tags > 0 else 0) * 20
                            score += personality_score

                        # Calculate location proximity (20% weight)
                        if user.location and current_user.location:
                            location_score = 20 if user.location == current_user.location else 10
                            score += location_score
                        
                        return min(round(score), 100)
                    def calculate_connection_strength(user, current_user):
                        """
                        Calculate connection strength based on:
                        - Mutual connections (30%)
                        - Common interests count (30%)
                        - Activity overlap (20%)
                        - Profile completeness (20%)
                        """
                        strength = 0
                        
                        # Calculate mutual connections score (30% weight)
                        user_connections = set(Connection.objects.filter(
                            Q(user1=user) | Q(user2=user),
                            is_active=True
                        ).values_list('user1_id', 'user2_id').distinct())
                        
                        current_user_connections = set(Connection.objects.filter(
                            Q(user1=current_user) | Q(user2=current_user),
                            is_active=True
                        ).values_list('user1_id', 'user2_id').distinct())
                        
                        mutual_connections = len(user_connections.intersection(current_user_connections))
                        max_mutual = min(len(user_connections), len(current_user_connections))
                        mutual_score = (mutual_connections / max_mutual if max_mutual > 0 else 0) * 30
                        strength += mutual_score

                        # Calculate common interests score (30% weight)
                        current_user_interests = set(current_user.interests.values_list('name', flat=True))
                        user_interests = set(user.interests.values_list('name', flat=True))
                        
                        if current_user_interests and user_interests:
                            common_interests = len(current_user_interests.intersection(user_interests))
                            max_interests = min(len(current_user_interests), len(user_interests))
                            interests_score = (common_interests / max_interests if max_interests > 0 else 0) * 30
                            strength += interests_score

                        # Calculate activity overlap (20% weight)
                        if user.last_active and current_user.last_active:
                            from datetime import timedelta
                            time_diff = abs((user.last_active - current_user.last_active).total_seconds())
                            activity_score = 20 if time_diff < timedelta(days=7).total_seconds() else \
                                            10 if time_diff < timedelta(days=30).total_seconds() else 5
                            strength += activity_score

                        # Calculate profile completeness (20% weight)
                        def get_profile_completion(u):
                            fields = ['first_name', 'last_name', 'avatar', 'role', 'location']
                            completed = sum(1 for f in fields if getattr(u, f))
                            return completed / len(fields)
                        
                        user_completion = get_profile_completion(user)
                        current_user_completion = get_profile_completion(current_user)
                        completion_score = ((user_completion + current_user_completion) / 2) * 20
                        strength += completion_score
                        
                        return min(round(strength), 100)

                    user_data = {
                        'id': str(user.id),
                        'first_name': str(user.first_name) if user.first_name else '',
                        'last_name': str(user.last_name) if user.last_name else '',
                        'username': str(user.username),
                        'avatar': str(user.avatar) if user.avatar else '',
                        'role': str(user.role) if user.role else 'AI Professional',
                        'personality_tags': personality_tags_data,
                        'badges': [str(badge) for badge in user.badges.all()] if hasattr(user, 'badges') else [],
                        'last_active': str(user.last_active) if user.last_active else 'Online',
                        'mutual_connections': mutual_connections,
                        'interests': interests_data,
                        'common_interests': common_interests,
                        'location': str(user.location) if user.location else 'Unknown Location',
                        'connection_status': 'connect',
                        'match_score': calculate_match_score(user, request.user),
                        'connection_strength': calculate_connection_strength(user, request.user)
                    }
                    discover_data.append(user_data)
                except Exception as field_error:
                    logger.error(f"Error processing user data: {str(field_error)}", exc_info=True)
                    continue

            return Response(discover_data)
        except Exception as e:
            logger.error(f"Error getting discover users: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Failed to get discover users'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def friends(self, request):
        """Get all accepted connections (friends) for the current user."""
        try:
            # Get all active connections where the current user is either user1 or user2
            connections = Connection.objects.filter(
                (models.Q(user1=request.user) | models.Q(user2=request.user)),
                is_active=True
            ).select_related('user1', 'user2').prefetch_related(
                'user1__interests',
                'user2__interests',
                'user1__personality_tags',
                'user2__personality_tags'
            )

            # For each connection, get the friend (the other user)
            friends_data = []
            for connection in connections:
                friend = connection.user2 if connection.user1 == request.user else connection.user1
                try:
                    # Get personality tags using the serializer
                    personality_tags = friend.personality_tags.all()
                    personality_tags_data = PersonalityTagSerializer(personality_tags, many=True).data

                    # Get user's interests using the serializer
                    user_interests = friend.interests.all()
                    interests_data = UserInterestSerializer(user_interests, many=True).data

                    # Get common interests from the connection
                    common_interests = connection.common_interests or []

                    # Ensure all text fields are properly encoded strings
                    friend_data = {
                        'id': str(friend.id),
                        'first_name': str(friend.first_name) if friend.first_name else '',
                        'last_name': str(friend.last_name) if friend.last_name else '',
                        'username': str(friend.username),
                        'avatar': str(friend.avatar) if friend.avatar else '',
                        'role': str(friend.role) if friend.role else 'AI Professional',
                        'personality_tags': personality_tags_data,
                        'badges': [str(badge) for badge in friend.badges.all()] if hasattr(friend, 'badges') else [],
                        'last_active': str(friend.last_active) if friend.last_active else 'Online',
                        'connected_since': connection.created_at.isoformat() if connection.created_at else None,
                        'connected_at': connection.created_at.isoformat() if connection.created_at else None,
                        'mutual_connections': int(connection.mutual_connections_count) if connection.mutual_connections_count is not None else 0,
                        'interests': interests_data,  # User's own interests
                        'common_interests': common_interests,  # Interests shared with current user
                        'location': str(friend.location) if friend.location else 'Unknown Location',
                        'last_interaction': connection.last_interaction.isoformat() if connection.last_interaction else None
                    }
                    friends_data.append(friend_data)
                except Exception as field_error:
                    logger.error(f"Error processing friend data: {str(field_error)}", exc_info=True)
                    continue

            return Response(friends_data)
        except Exception as e:
            logger.error(f"Error getting friends: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Failed to get friends'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def update_strength(self, request, pk=None):
        try:
            connection = self.get_object()
            strength = request.data.get('strength')
            if strength is not None and 0 <= strength <= 100:
                connection.connection_strength = strength
                connection.save()
                return Response(self.get_serializer(connection).data)
            return Response(
                {'error': 'Invalid strength value'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error in update_strength: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def update_connection_match_score(self, connection):
        """Update the match score for a connection based on various factors."""
        try:
            user1 = connection.user1
            user2 = connection.user2

            # Get user interests
            user1_interests = set(user1.interests.values_list('name', flat=True))
            user2_interests = set(user2.interests.values_list('name', flat=True))
            common_interests = list(user1_interests.intersection(user2_interests))

            # Calculate interest similarity
            interest_similarity = len(common_interests) / max(len(user1_interests), len(user2_interests)) if user1_interests or user2_interests else 0

            # Calculate mutual connections
            mutual_connections = Connection.objects.filter(
                Q(user1=user1) | Q(user2=user1),
                is_active=True
            ).filter(
                Q(user1=user2) | Q(user2=user2)
            ).count()

            # Calculate network score
            network_score = min(mutual_connections / 10, 1) if mutual_connections > 0 else 0

            # Calculate activity score
            user1_activity = user1.last_login.timestamp() if user1.last_login else 0
            user2_activity = user2.last_login.timestamp() if user2.last_login else 0
            max_activity = max(user1_activity, user2_activity)
            activity_score = ((user1_activity / max_activity) + (user2_activity / max_activity)) / 2 if max_activity > 0 else 0

            # Calculate location score
            user1_location = getattr(user1, 'location', '').lower()
            user2_location = getattr(user2, 'location', '').lower()
            location_score = 1.0 if user1_location == user2_location else (0.7 if user1_location in user2_location or user2_location in user1_location else 0.3)

            # Calculate education score
            user1_field = getattr(user1, 'field_of_study', '').lower()
            user2_field = getattr(user2, 'field_of_study', '').lower()
            user1_institution = getattr(user1, 'institution', '').lower()
            user2_institution = getattr(user2, 'institution', '').lower()
            
            education_score = 0
            factors = 0
            
            if user1_field and user2_field:
                if user1_field == user2_field:
                    education_score += 1.0
                elif any(word in user2_field for word in user1_field.split()) or any(word in user1_field for word in user2_field.split()):
                    education_score += 0.7
                factors += 1
            
            if user1_institution and user2_institution:
                if user1_institution == user2_institution:
                    education_score += 1.0
                elif any(word in user2_institution for word in user1_institution.split()) or any(word in user1_institution for word in user2_institution.split()):
                    education_score += 0.7
                factors += 1
            
            education_score = education_score / max(factors, 1) if factors > 0 else 0.3

            # Calculate final match score with weights
            final_score = (
                interest_similarity * 0.25 +     # Interest similarity
                network_score * 0.25 +          # Network score
                activity_score * 0.15 +         # Activity score
                location_score * 0.20 +         # Location score
                education_score * 0.15          # Education score
            )

            # Update connection with new match score and common interests
            connection.match_score = round(final_score * 100)  # Convert to percentage
            connection.common_interests = common_interests
            connection.mutual_connections_count = mutual_connections
            connection.save()

        except Exception as e:
            logger.error(f"Error updating connection match score: {str(e)}", exc_info=True)

    def perform_create(self, serializer):
        """Override perform_create to update match score after connection creation."""
        connection = serializer.save()
        self.update_connection_match_score(connection)

    @action(detail=True, methods=['post'])
    def accept_request(self, request, pk=None):
        """Accept a connection request and create a new connection."""
        try:
            connection_request = ConnectionRequest.objects.get(id=pk, receiver=request.user, status='pending')
            
            # Create the connection
            connection = Connection.objects.create(
                user1=connection_request.sender,
                user2=connection_request.receiver,
                is_active=True
            )
            
            # Update the match score
            self.update_connection_match_score(connection)
            
            # Update the request status
            connection_request.status = 'accepted'
            connection_request.save()
            
            return Response(self.get_serializer(connection).data)
        except ConnectionRequest.DoesNotExist:
            return Response(
                {'error': 'Connection request not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error accepting connection request: {str(e)}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ConnectionRequestViewSet(viewsets.ModelViewSet):
    serializer_class = ConnectionRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        try:
            return ConnectionRequest.objects.filter(
                models.Q(sender=self.request.user) | 
                models.Q(receiver=self.request.user)
            )
        except Exception as e:
            logger.error(f"Error in ConnectionRequestViewSet.get_queryset: {str(e)}")
            raise

    def perform_create(self, serializer):
        try:
            logger.info("\n=== Starting Connection Request Creation ===")
            
            # Check if a pending connection request already exists
            receiver_id = serializer.validated_data.get('receiver_id')
            logger.info(f"Checking for existing request between sender {self.request.user.id} and receiver {receiver_id}")
            
            existing_request = ConnectionRequest.objects.filter(
                sender=self.request.user,
                receiver_id=receiver_id,
                status='pending'
            ).first()
            
            if existing_request:
                logger.info(f"Found existing request {existing_request.id}, returning it")
                return existing_request
            
            # Create new request
            request = serializer.save(sender=self.request.user)
            logger.info(f"Created new connection request {request.id}")
            
            # Calculate match score and connection strength
            def calculate_match_score(user1, user2):
                """
                Calculate match score based on:
                - Common interests (40%)
                - Role compatibility (20%)
                - Personality tags overlap (20%)
                - Location proximity (20%)
                """
                logger.info(f"\n=== Calculating Match Score ===")
                logger.info(f"User1: {user1.username}, User2: {user2.username}")
                
                score = 0
                
                # Calculate interests match (40% weight)
                user1_interests = set(user1.interests.values_list('name', flat=True))
                user2_interests = set(user2.interests.values_list('name', flat=True))
                
                logger.info(f"User1 interests: {user1_interests}")
                logger.info(f"User2 interests: {user2_interests}")
                
                if user1_interests and user2_interests:
                    common_interests = len(user1_interests.intersection(user2_interests))
                    total_interests = len(user1_interests.union(user2_interests))
                    interests_score = (common_interests / total_interests if total_interests > 0 else 0) * 40
                    score += interests_score
                    logger.info(f"Interests score: {interests_score} (based on {common_interests} common out of {total_interests} total)")

                # Calculate role compatibility (20% weight)
                if user1.role and user2.role:
                    role_score = 20 if user1.role == user2.role else 10
                    score += role_score
                    logger.info(f"Role score: {role_score} (User1: {user1.role}, User2: {user2.role})")

                # Calculate personality tags overlap (20% weight)
                user1_tags = set(user1.personality_tags.values_list('name', flat=True))
                user2_tags = set(user2.personality_tags.values_list('name', flat=True))
                
                logger.info(f"User1 personality tags: {user1_tags}")
                logger.info(f"User2 personality tags: {user2_tags}")
                
                if user1_tags and user2_tags:
                    common_tags = len(user1_tags.intersection(user2_tags))
                    total_tags = len(user1_tags.union(user2_tags))
                    personality_score = (common_tags / total_tags if total_tags > 0 else 0) * 20
                    score += personality_score
                    logger.info(f"Personality score: {personality_score} (based on {common_tags} common out of {total_tags} total)")

                # Calculate location proximity (20% weight)
                if user1.location and user2.location:
                    location_score = 20 if user1.location == user2.location else 10
                    score += location_score
                    logger.info(f"Location score: {location_score} (User1: {user1.location}, User2: {user2.location})")
                
                final_score = min(round(score), 100)
                logger.info(f"Final match score: {final_score}")
                return final_score

            def calculate_connection_strength(user1, user2):
                """
                Calculate connection strength based on:
                - Mutual connections (30%)
                - Common interests count (30%)
                - Activity overlap (20%)
                - Profile completeness (20%)
                """
                logger.info(f"\n=== Calculating Connection Strength ===")
                logger.info(f"User1: {user1.username}, User2: {user2.username}")
                
                strength = 0
                
                # Calculate mutual connections score (30% weight)
                user1_connections = set(Connection.objects.filter(
                    models.Q(user1=user1) | models.Q(user2=user1),
                    is_active=True
                ).values_list('user1_id', 'user2_id').distinct())
                
                user2_connections = set(Connection.objects.filter(
                    models.Q(user1=user2) | models.Q(user2=user2),
                    is_active=True
                ).values_list('user1_id', 'user2_id').distinct())
                
                mutual_connections = len(user1_connections.intersection(user2_connections))
                max_mutual = min(len(user1_connections), len(user2_connections))
                mutual_score = (mutual_connections / max_mutual if max_mutual > 0 else 0) * 30
                strength += mutual_score
                
                logger.info(f"Mutual connections score: {mutual_score} (based on {mutual_connections} mutual out of max {max_mutual})")

                # Calculate common interests score (30% weight)
                user1_interests = set(user1.interests.values_list('name', flat=True))
                user2_interests = set(user2.interests.values_list('name', flat=True))
                
                if user1_interests and user2_interests:
                    common_interests = len(user1_interests.intersection(user2_interests))
                    max_interests = min(len(user1_interests), len(user2_interests))
                    interests_score = (common_interests / max_interests if max_interests > 0 else 0) * 30
                    strength += interests_score
                    logger.info(f"Common interests score: {interests_score} (based on {common_interests} common out of max {max_interests})")

                # Calculate activity overlap (20% weight)
                if user1.last_active and user2.last_active:
                    from datetime import timedelta
                    time_diff = abs((user1.last_active - user2.last_active).total_seconds())
                    activity_score = 20 if time_diff < timedelta(days=7).total_seconds() else \
                                    10 if time_diff < timedelta(days=30).total_seconds() else 5
                    strength += activity_score
                    logger.info(f"Activity score: {activity_score} (time difference: {time_diff} seconds)")

                # Calculate profile completeness (20% weight)
                def get_profile_completion(u):
                    fields = ['first_name', 'last_name', 'avatar', 'role', 'location']
                    completed = sum(1 for f in fields if getattr(u, f))
                    return completed / len(fields)
                
                user1_completion = get_profile_completion(user1)
                user2_completion = get_profile_completion(user2)
                completion_score = ((user1_completion + user2_completion) / 2) * 20
                strength += completion_score
                
                logger.info(f"Profile completion score: {completion_score} (User1: {user1_completion * 100}%, User2: {user2_completion * 100}%)")
                
                final_strength = min(round(strength), 100)
                logger.info(f"Final connection strength: {final_strength}")
                return final_strength

            # Calculate match score and connection strength
            match_score = calculate_match_score(self.request.user, request.receiver)
            connection_strength = calculate_connection_strength(self.request.user, request.receiver)
            
            logger.info(f"\n=== Final Scores ===")
            logger.info(f"Match Score: {match_score}")
            logger.info(f"Connection Strength: {connection_strength}")
            
            # Calculate common interests
            user1_interests = set(self.request.user.interests.values_list('name', flat=True))
            user2_interests = set(request.receiver.interests.values_list('name', flat=True))
            common_interests = list(user1_interests.intersection(user2_interests))
            
            # Calculate mutual connections
            user1_connections = set(Connection.objects.filter(
                models.Q(user1=self.request.user) | models.Q(user2=self.request.user),
                is_active=True
            ).values_list('user1_id', 'user2_id').distinct())
            
            user2_connections = set(Connection.objects.filter(
                models.Q(user1=request.receiver) | models.Q(user2=request.receiver),
                is_active=True
            ).values_list('user1_id', 'user2_id').distinct())
            
            mutual_connections = len(user1_connections.intersection(user2_connections))
            
            # Update the request with calculated values
            request.match_score = match_score
            request.connection_strength = connection_strength
            request.common_interests = common_interests
            request.mutual_connections = mutual_connections
            request.save()
            
            logger.info(f"\n=== Connection Request Updated ===")
            logger.info(f"Request ID: {request.id}")
            logger.info(f"Match Score: {request.match_score}")
            logger.info(f"Connection Strength: {request.connection_strength}")
            logger.info(f"Common Interests: {request.common_interests}")
            logger.info(f"Mutual Connections: {request.mutual_connections}")
            
            return request
        except Exception as e:
            logger.error(f"Error in perform_create: {str(e)}", exc_info=True)
            raise

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        try:
            logger.info(f"[Backend] Accepting connection request {pk} for user {request.user.id}")
            connection_request = self.get_object()
            
            if connection_request.receiver != request.user:
                logger.warning(f"[Backend] Unauthorized accept attempt: User {request.user.id} tried to accept request {pk} for user {connection_request.receiver.id}")
                return Response(
                    {'error': 'Not authorized'}, 
                    status=status.HTTP_403_FORBIDDEN
                )

            # Create the connection
            connection = connection_request.accept()
            logger.info(f"[Backend] Successfully created connection between users {connection.user1.id} and {connection.user2.id}")
            logger.info(f"[Backend] Connection details - Strength: {connection.connection_strength}, Match Score: {connection.match_score}")
            logger.info(f"[Backend] Common Interests: {connection.common_interests}")
            logger.info(f"[Backend] Mutual Connections: {connection.mutual_connections_count}")

            # Update connection request status
            connection_request.status = 'accepted'
            connection_request.save()
            logger.info(f"[Backend] Updated connection request {pk} status to accepted")

            return Response(self.get_serializer(connection_request).data)
            
        except Exception as e:
            logger.error(f"[Backend] Error in accept: {str(e)}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        try:
            logger.info(f"[Backend] Rejecting connection request {pk} for user {request.user.id}")
            connection_request = self.get_object()
            
            if connection_request.receiver != request.user:
                logger.warning(f"[Backend] Unauthorized reject attempt: User {request.user.id} tried to reject request {pk} for user {connection_request.receiver.id}")
                return Response(
                    {'error': 'Not authorized'}, 
                    status=status.HTTP_403_FORBIDDEN
                )

            # Delete the request instead of updating status
            connection_request.delete()
            logger.info(f"[Backend] Successfully deleted connection request {pk}")
            
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.error(f"[Backend] Error in reject: {str(e)}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        try:
            try:
                connection_request = self.get_object()
            except ObjectDoesNotExist:
                logger.error(f"Connection request {pk} not found")
                return Response(
                    {'error': 'Connection request not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )

            if connection_request.sender != request.user:
                logger.warning(f"User {request.user.id} attempted to cancel request {pk} they didn't send")
                return Response(
                    {'error': 'Not authorized'}, 
                    status=status.HTTP_403_FORBIDDEN
                )

            if connection_request.status != 'pending':
                logger.warning(f"Attempted to cancel non-pending request {pk} with status {connection_request.status}")
                return Response(
                    {'error': 'Can only cancel pending requests'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                # Delete the request instead of updating status
                connection_request.delete()
                logger.info(f"Successfully deleted connection request {pk}")
                return Response(status=status.HTTP_204_NO_CONTENT)
            except Exception as delete_error:
                logger.error(f"Error deleting connection request {pk}: {str(delete_error)}")
                return Response(
                    {'error': 'Failed to delete connection request'}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except Exception as e:
            logger.error(f"Unexpected error in cancel for request {pk}: {str(e)}", exc_info=True)
            return Response(
                {'error': 'An unexpected error occurred'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class UserSuggestionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserSuggestionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        try:
            page = int(self.request.query_params.get('page', 1))
            page_size = int(self.request.query_params.get('page_size', 20))
            
            logger.info(f"Fetching suggestions for user: {self.request.user.id} - Page {page}")
            queryset = UserSuggestion.objects.filter(
                user=self.request.user,
                is_active=True
            ).select_related('suggested_user')
            
            # If no suggestions exist, generate them
            if not queryset.exists():
                logger.info(f"No suggestions found for user {self.request.user.id}, generating new suggestions")
                try:
                    from connections.services import generate_user_suggestions
                    suggestions, total = generate_user_suggestions(self.request.user, page=page, page_size=page_size)
                    # Fetch the newly generated suggestions
                    queryset = UserSuggestion.objects.filter(
                        user=self.request.user,
                        is_active=True
                    ).select_related('suggested_user')
                except Exception as e:
                    logger.error(f"Error generating suggestions: {str(e)}", exc_info=True)
                    return UserSuggestion.objects.none()
            
            logger.info(f"Found {queryset.count()} suggestions")
            return queryset
        except Exception as e:
            logger.error(f"Error in UserSuggestionViewSet.get_queryset: {str(e)}", exc_info=True)
            return UserSuggestion.objects.none()

    def list(self, request, *args, **kwargs):
        try:
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 20))
            
            queryset = self.get_queryset()
            
            # Get total count for pagination
            total_count = queryset.count()
            
            # Apply pagination
            start = (page - 1) * page_size
            end = start + page_size
            paginated_queryset = queryset[start:end]
            
            serializer = self.get_serializer(paginated_queryset, many=True)
            
            return Response({
                'results': serializer.data,
                'total': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': (total_count + page_size - 1) // page_size
            })
        except Exception as e:
            logger.error(f"Error in UserSuggestionViewSet.list: {str(e)}", exc_info=True)
            return Response({
                'results': [],
                'total': 0,
                'page': 1,
                'page_size': page_size,
                'total_pages': 0
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def refresh(self, request):
        try:
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 20))
            
            logger.info(f"Refreshing suggestions for user: {request.user.id} - Page {page}")
            # Deactivate existing suggestions
            UserSuggestion.objects.filter(user=request.user).update(is_active=False)
            
            # Generate new suggestions
            from connections.services import generate_user_suggestions
            suggestions, total = generate_user_suggestions(request.user, page=page, page_size=page_size)
            
            # Return the new suggestions
            queryset = self.get_queryset()
            
            # Apply pagination
            start = (page - 1) * page_size
            end = start + page_size
            paginated_queryset = queryset[start:end]
            
            serializer = self.get_serializer(paginated_queryset, many=True)
            
            return Response({
                'results': serializer.data,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size
            })
        except Exception as e:
            logger.error(f"Error in refresh suggestions: {str(e)}", exc_info=True)
            return Response(
                {
                    'error': str(e),
                    'detail': 'Failed to refresh suggestions. Please try again later.'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
