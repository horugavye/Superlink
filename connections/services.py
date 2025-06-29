import requests
from django.conf import settings
from django.db.models import Q, Count
from .models import UserSuggestion, Connection, ConnectionRequest
from django.contrib.auth import get_user_model
import logging
import json
import os
from collections import defaultdict
from math import log
from django.utils import timezone
from datetime import timedelta
from mistralai import Mistral
from chat.models import Message, Conversation
from assistant.models import ChatMessage

logger = logging.getLogger(__name__)

User = get_user_model()

def get_mistral_client():
    """
    Returns a new Mistral client using a hardcoded API key.
    """
    api_key = "4Q6ICI5AWFuwfuD5bu4cpPTWOKRbyDEY"
    return Mistral(api_key=api_key)

def calculate_tfidf_score(interest, all_users_interests):
    """
    Calculate TF-IDF score for an interest based on its frequency across all users
    """
    total_users = len(all_users_interests)
    users_with_interest = sum(1 for interests in all_users_interests if interest in interests)
    if users_with_interest == 0:
        return 0
    return log(total_users / users_with_interest)


def calculate_network_score(user, potential_user, existing_connections):
    """
    Calculate network score based on mutual connections and connection patterns
    """
    user_connections = set()
    potential_connections = set()
    
    for conn in existing_connections:
        if conn[0] == user.id:
            user_connections.add(conn[1])
        elif conn[1] == user.id:
            user_connections.add(conn[0])
        if conn[0] == potential_user.id:
            potential_connections.add(conn[1])
        elif conn[1] == potential_user.id:
            potential_connections.add(conn[0])
    
    mutual_connections = len(user_connections.intersection(potential_connections))
    total_connections = len(user_connections.union(potential_connections))
    
    if total_connections == 0:
        return 0
    
    return mutual_connections / total_connections


def calculate_activity_score(user, potential_user):
    """
    Calculate activity score based on user engagement and interaction patterns
    """
    user_activity = user.last_login.timestamp() if user.last_login else 0
    potential_activity = potential_user.last_login.timestamp() if potential_user.last_login else 0
    
    # Normalize activity scores to 0-1 range
    max_activity = max(user_activity, potential_activity)
    if max_activity == 0:
        return 0
    
    user_score = user_activity / max_activity
    potential_score = potential_activity / max_activity
    
    return (user_score + potential_score) / 2


def calculate_location_score(user, potential_user):
    """
    Calculate location similarity score based on user locations.
    Higher score for same city, medium for same region/country, lower for different countries.
    """
    try:
        user_location = getattr(user, 'location', '').lower()
        potential_location = getattr(potential_user, 'location', '').lower()
        
        if not user_location or not potential_location:
            return 0.3  # Default score if location not set
            
        # Exact match (same city)
        if user_location == potential_location:
            return 1.0
            
        # Same region/country (check if one location contains the other)
        if user_location in potential_location or potential_location in user_location:
            return 0.7
            
        # Different locations
        return 0.3
        
    except Exception as e:
        logger.warning(f"Error calculating location score: {str(e)}")
        return 0.3


def calculate_education_score(user, potential_user):
    """
    Calculate education similarity score based on user education fields.
    Considers field of study, degree level, and institution.
    """
    try:
        score = 0.0
        factors = 0
        
        # Field of study similarity
        user_field = getattr(user, 'field_of_study', '').lower()
        potential_field = getattr(potential_user, 'field_of_study', '').lower()
        if user_field and potential_field:
            if user_field == potential_field:
                score += 1.0
            elif any(word in potential_field for word in user_field.split()) or \
                 any(word in user_field for word in potential_field.split()):
                score += 0.7
            factors += 1
        
        # Degree level similarity
        user_degree = getattr(user, 'degree_level', '').lower()
        potential_degree = getattr(potential_user, 'degree_level', '').lower()
        if user_degree and potential_degree:
            if user_degree == potential_degree:
                score += 1.0
            factors += 1
        
        # Institution similarity
        user_institution = getattr(user, 'institution', '').lower()
        potential_institution = getattr(potential_user, 'institution', '').lower()
        if user_institution and potential_institution:
            if user_institution == potential_institution:
                score += 1.0
            elif any(word in potential_institution for word in user_institution.split()) or \
                 any(word in user_institution for word in potential_institution.split()):
                score += 0.7
            factors += 1
        
        return score / max(factors, 1) if factors > 0 else 0.3
        
    except Exception as e:
        logger.warning(f"Error calculating education score: {str(e)}")
        return 0.3


def mark_user_as_rejected(user, rejected_user):
    """
    Mark a user as rejected in the suggestions system
    """
    try:
        # Update or create the suggestion with rejected status
        suggestion, created = UserSuggestion.objects.update_or_create(
            user=user,
            suggested_user=rejected_user,
            defaults={
                'is_active': False,
                'is_rejected': True,
                'rejected_at': timezone.now()
            }
        )
        logger.info(f"Marked user {rejected_user.id} as rejected for user {user.id}")
        return True
    except Exception as e:
        logger.error(f"Error marking user as rejected: {str(e)}", exc_info=True)
        return False


# Helper to generate AI explanation for a match using Mistral
# Helper to generate AI explanation for a match using OpenRouter (OpenAI)
def get_ai_match_explanation(user, potential_user, common_interests, location_score, education_score, is_alchemy=False):
    client = get_mistral_client()
    if not client:
        logger.error("Mistral client not available.")
        return None
    # Build prompt
    if is_alchemy:
        prompt = f"""
User 1: {user.username}, Interests: {', '.join(common_interests)}, Location: {getattr(user, 'location', '')}, Education: {getattr(user, 'field_of_study', '')} at {getattr(user, 'institution', '')}
User 2: {potential_user.username}, Interests: {', '.join(common_interests)}, Location: {getattr(potential_user, 'location', '')}, Education: {getattr(potential_user, 'field_of_study', '')} at {getattr(potential_user, 'institution', '')}
Explain in 1-2 sentences why these users would be a good match, focusing on not only their shared interests, location, and background, but also on how their different skills, professions, or experiences could help each other on projects or new opportunities. Suggest creative or unexpected ways they could collaborate, even if their backgrounds are very different. Make sure to mention that they are not currently related but could help each other if they connect.
"""
    else:
        prompt = f"""
User 1: {user.username}, Interests: {', '.join(common_interests)}, Location: {getattr(user, 'location', '')}, Education: {getattr(user, 'field_of_study', '')} at {getattr(user, 'institution', '')}
User 2: {potential_user.username}, Interests: {', '.join(common_interests)}, Location: {getattr(potential_user, 'location', '')}, Education: {getattr(potential_user, 'field_of_study', '')} at {getattr(potential_user, 'institution', '')}
Explain in 1-2 sentences why these users would be a good match, focusing on their shared interests, location, and background. You may also mention if their different backgrounds could lead to creative or mutually beneficial collaborations.
"""
    try:
        response = client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "user", "content": prompt}]
        )
        explanation = response.choices[0].message.content.strip()
        return explanation
    except Exception as e:
        logger.error(f"Mistral API error: {str(e)}", exc_info=True)
        return None


def generate_user_suggestions(user, page=1, page_size=20, purpose_text=None):
    """
    Generate user suggestions based on advanced algorithm incorporating multiple factors.
    Now includes location and education as significant factors.
    Also ensures the best interest alchemy suggestion is included.
    """
    try:
        if not user or not user.is_authenticated:
            logger.error("Invalid or unauthenticated user")
            return [], 0
        
        logger.info(f"Starting advanced suggestion generation for user: {user.username} (ID: {user.id}) - Page {page}")
        
        # --- Ensure interest alchemy suggestion is created first ---
        if purpose_text is None:
            purpose_text = "find the most interesting connection"
        best_user, best_score = get_interest_alchemy_suggestion(user, purpose_text)
        alchemy_suggestion = None
        if best_user is not None:
            try:
                alchemy_suggestion = UserSuggestion.objects.get(user=user, suggested_user=best_user, is_active=True)
            except UserSuggestion.DoesNotExist:
                alchemy_suggestion = None

        # Calculate offset for pagination
        offset = (page - 1) * page_size
    
        # Get user's existing connections and requests with connection strength
        try:
            existing_connections = Connection.objects.filter(
                Q(user1=user) | Q(user2=user)
            ).values_list('user1_id', 'user2_id', 'connection_strength')
            logger.info(f"Found {len(existing_connections)} existing connections")
        except Exception as e:
            logger.error(f"Error fetching existing connections: {str(e)}", exc_info=True)
            existing_connections = []
        
        # Build connection strength map and get user's connections
        connection_strengths = {}
        user_connections = set()
        for u1, u2, strength in existing_connections:
            other_user = u2 if u1 == user.id else u1
            connection_strengths[other_user] = strength
            user_connections.add(other_user)
        
        # Get IDs of users we're already connected with
        connected_user_ids = user_connections.copy()

        # Add users from accepted connection requests
        try:
            accepted_requests = ConnectionRequest.objects.filter(
                (Q(sender=user) | Q(receiver=user)) & Q(status='accepted')
            ).values_list('sender_id', 'receiver_id')
            for s, r in accepted_requests:
                connected_user_ids.add(s)
                connected_user_ids.add(r)
            logger.info(f"Added {len(accepted_requests)} accepted connection requests to exclusion list")
        except Exception as e:
            logger.error(f"Error fetching accepted connections: {str(e)}", exc_info=True)
        
        # Get IDs of users we have pending requests with
        try:
            pending_requests = ConnectionRequest.objects.filter(
                (Q(sender=user) | Q(receiver=user)) & Q(status='pending')
            ).values_list('sender_id', 'receiver_id')
            logger.info(f"Found {len(pending_requests)} pending requests")
        except Exception as e:
            logger.error(f"Error fetching pending requests: {str(e)}", exc_info=True)
            pending_requests = []
        
        # Combine all excluded user IDs
        excluded_ids = connected_user_ids.union(set(s for s, r in pending_requests))
        
        # Get all potential users excluding connected and rejected
        try:
            potential_users = User.objects.exclude(
                id__in=excluded_ids
            ).exclude(
                id=user.id
            ).order_by('-last_login', 'id')
            
            total_users = potential_users.count()
            logger.info(f"Found {total_users} potential users for suggestions")
            
            if not potential_users.exists():
                logger.info(f"No potential users found for user {user.id}")
                return [], 0
        except Exception as e:
            logger.error(f"Error fetching potential users: {str(e)}", exc_info=True)
            return [], 0
        
        # Get user's interests
        user_interests = set()
        try:
            user_interests = set(interest.name for interest in user.interests.all())
            logger.info(f"User {user.id} has {len(user_interests)} interests: {user_interests}")
        except Exception as e:
            logger.warning(f"Could not get interests for user {user.id}: {str(e)}")
            user_interests = set()
        
        # Get potential users' interests and connections
        potential_user_data = {}
        for p_user in potential_users:
            try:
                # Get interests
                interests = set()
                try:
                    interests = set(interest.name for interest in p_user.interests.all())
                    logger.info(f"Potential user {p_user.id} has {len(interests)} interests: {interests}")
                except Exception as e:
                    logger.warning(f"Could not get interests for potential user {p_user.id}: {str(e)}")
                    interests = set()
                
                # Get user's connections
                p_user_connections = set()
                for u1, u2, _ in existing_connections:
                    if u1 == p_user.id:
                        p_user_connections.add(u2)
                    elif u2 == p_user.id:
                        p_user_connections.add(u1)
                
                potential_user_data[p_user.id] = {
                    'interests': interests,
                    'connections': p_user_connections
                }
                
            except Exception as e:
                logger.warning(f"Could not get data for potential user {p_user.id}: {str(e)}")
                potential_user_data[p_user.id] = {
                    'interests': set(),
                    'connections': set()
                }
        
        # Calculate scores and create suggestions
        suggestions_created = []
        for potential_user in potential_users:
            try:
                p_user_data = potential_user_data[potential_user.id]
                
                # Calculate common interests with detailed logging
                logger.info(f"\n=== Processing User {potential_user.username} ===")
                logger.info(f"Current user interests: {user_interests}")
                logger.info(f"Potential user interests: {p_user_data['interests']}")
                
                common_interests = list(user_interests.intersection(p_user_data['interests']))
                logger.info(f"Common interests found: {common_interests}")
                logger.info(f"Number of common interests: {len(common_interests)}")
                
                # Calculate mutual connections
                mutual_connections = len(user_connections.intersection(p_user_data['connections']))
                logger.info(f"Mutual connections: {mutual_connections}")
                
                # Calculate interest similarity using TF-IDF
                interest_score = 0
                for interest in common_interests:
                    score = calculate_tfidf_score(interest, [data['interests'] for data in potential_user_data.values()])
                    interest_score += score
                    logger.info(f"TF-IDF score for interest '{interest}': {score}")
                
                logger.info(f"Total interest score: {interest_score}")
                
                # Calculate network score
                network_score = calculate_network_score(user, potential_user, existing_connections)
                logger.info(f"Network score: {network_score}")
                
                # Calculate activity score
                activity_score = calculate_activity_score(user, potential_user)
                logger.info(f"Activity score: {activity_score}")
                
                # Calculate location score
                location_score = calculate_location_score(user, potential_user)
                logger.info(f"Location score: {location_score}")
                
                # Calculate education score
                education_score = calculate_education_score(user, potential_user)
                logger.info(f"Education score: {education_score}")
                
                # Calculate final score with updated weights
                final_score = (
                    interest_score * 0.25 +     # Interest similarity weight (reduced)
                    network_score * 0.25 +      # Network score weight (reduced)
                    activity_score * 0.15 +     # Activity score weight (reduced)
                    location_score * 0.20 +     # Location score weight (new)
                    education_score * 0.15      # Education score weight (new)
                )
                
                # Normalize score to 0-1 range and convert to percentage (0-100)
                final_score = round(min(max(final_score, 0), 1) * 100)
                logger.info(f"Final match score: {final_score}%")
                
                # --- AI explanation integration ---
                match_highlights = []
                ai_explanation = None
                if (len(common_interests) > 0 or location_score >= 0.7 or education_score >= 0.7):
                    ai_explanation = get_ai_match_explanation(user, potential_user, common_interests, location_score, education_score, is_alchemy=False)
                    if ai_explanation:
                        match_highlights = [ai_explanation]
                # If no AI explanation, match_highlights remains empty
                
                # Create or update the suggestion
                suggestion, created = UserSuggestion.objects.update_or_create(
                    user=user,
                    suggested_user=potential_user,
                    defaults={
                        'score': final_score,
                        'match_highlights': match_highlights,
                        'common_interests': common_interests,
                        'mutual_connections': mutual_connections,
                        'is_active': True
                    }
                )
                
                logger.info(f"Created suggestion for {potential_user.username}")
                logger.info(f"- Common interests: {len(common_interests)}")
                logger.info(f"- Location score: {location_score}")
                logger.info(f"- Education score: {education_score}")
                logger.info(f"- Final match score: {final_score}%")
                suggestions_created.append(suggestion)
                
            except Exception as e:
                logger.error(f"Error processing potential user {potential_user.id}: {str(e)}", exc_info=True)
                continue
        
        # Now apply pagination to suggestions_created (if needed)
        paginated_suggestions = suggestions_created[offset:offset+page_size]

        # --- Ensure alchemy suggestion is appended after paginated suggestions ---
        # Only append if alchemy_suggestion exists and is not already in paginated_suggestions
        if alchemy_suggestion is not None:
            already_included = any(
                s.suggested_user_id == alchemy_suggestion.suggested_user_id for s in paginated_suggestions
            )
            if not already_included:
                paginated_suggestions.append(alchemy_suggestion)

        return paginated_suggestions, total_users
        
    except Exception as e:
        logger.error(f"Error in generate_user_suggestions: {str(e)}", exc_info=True)
        return [], 0

def get_interest_alchemy_suggestion(user, purpose_text, model="mistral-large-latest"):
    """
    Use Mistral AI to find the best match for a user based on a specific purpose/goal.
    Considers interests, goals, location, and chat history.
    Returns the best matching user and their score.
    Only saves the suggestion to UserSuggestion if an AI explanation is successfully generated (i.e., credits are sufficient).
    """
    client = get_mistral_client()
    if not client:
        return None, None

    # Exclude self and already connected users
    try:
        existing_connections = Connection.objects.filter(
            Q(user1=user) | Q(user2=user)
        ).values_list('user1_id', 'user2_id')
        connected_user_ids = set()
        for u1, u2 in existing_connections:
            other_user = u2 if u1 == user.id else u1
            connected_user_ids.add(other_user)
        connected_user_ids.add(user.id)
    except Exception as e:
        logger.error(f"Error fetching existing connections: {str(e)}", exc_info=True)
        connected_user_ids = {user.id}

    potential_users = User.objects.exclude(id__in=connected_user_ids)
    best_score = -1
    best_user = None

    for potential_user in potential_users:
        # Gather data
        user_interests = ', '.join(i.name for i in getattr(user, 'interests', []).all()) if hasattr(user, 'interests') else ''
        user_goals = getattr(user, 'goals', '')
        user_location = getattr(user, 'location', '')
        potential_interests = ', '.join(i.name for i in getattr(potential_user, 'interests', []).all()) if hasattr(potential_user, 'interests') else ''
        potential_goals = getattr(potential_user, 'goals', '')
        potential_location = getattr(potential_user, 'location', '')

        # Fetch recent direct chat history between user and potential_user
        chat_history = []
        try:
            conversation = Conversation.objects.filter(
                type='direct',
                participant1__in=[user, potential_user],
                participant2__in=[user, potential_user]
            ).first()
            if conversation:
                messages = Message.objects.filter(conversation=conversation).order_by('-created_at')[:10]
                chat_history = [
                    f"{msg.sender.username}: {msg.content[:100]}" for msg in reversed(messages)
                ]
        except Exception as e:
            logger.warning(f"Could not fetch chat history for users {user.id} and {potential_user.id}: {str(e)}")
            chat_history = []
        if chat_history:
            chat_summary = '\n'.join(chat_history)
            chat_prompt = f"\nRecent chat history between these users (most recent last):\n{chat_summary}"
        else:
            chat_prompt = "\nNo prior chat history between these users."

        # Fetch recent assistant chat history for both users
        assistant_history_user = []
        assistant_history_potential = []
        try:
            user_msgs = ChatMessage.objects.filter(user=user).order_by('-timestamp')[:5]
            assistant_history_user = [
                f"User: {m.message[:100]}" if m.is_user_message else f"AI: {m.response[:100] if m.response else ''}" for m in reversed(user_msgs)
            ]
        except Exception as e:
            logger.warning(f"Could not fetch assistant chat for user {user.id}: {str(e)}")
            assistant_history_user = []
        try:
            pot_msgs = ChatMessage.objects.filter(user=potential_user).order_by('-timestamp')[:5]
            assistant_history_potential = [
                f"User: {m.message[:100]}" if m.is_user_message else f"AI: {m.response[:100] if m.response else ''}" for m in reversed(pot_msgs)
            ]
        except Exception as e:
            logger.warning(f"Could not fetch assistant chat for user {potential_user.id}: {str(e)}")
            assistant_history_potential = []
        if assistant_history_user:
            assistant_user_prompt = '\n'.join(assistant_history_user)
            assistant_user_prompt = f"\nRecent assistant chat for {user.username}:\n{assistant_user_prompt}"
        else:
            assistant_user_prompt = f"\nNo recent assistant chat for {user.username}."
        if assistant_history_potential:
            assistant_pot_prompt = '\n'.join(assistant_history_potential)
            assistant_pot_prompt = f"\nRecent assistant chat for {potential_user.username}:\n{assistant_pot_prompt}"
        else:
            assistant_pot_prompt = f"\nNo recent assistant chat for {potential_user.username}."

        prompt = f"""
User 1: {user.username}, Interests: {user_interests}, Goals: {user_goals}, Location: {user_location}
User 2: {potential_user.username}, Interests: {potential_interests}, Goals: {potential_goals}, Location: {potential_location}
User 1 is looking for: {purpose_text}
{chat_prompt}
{assistant_user_prompt}
{assistant_pot_prompt}
On a scale of 0 to 100, how strong is the match between these users for this purpose? Consider not only similar backgrounds and interests, but also how their different skills, professions, or experiences could help each other on projects or new opportunities. Respond with only the number.
"""
        try:
            response = client.chat.complete(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            score_str = response.choices[0].message.content.strip()
            # Extract the first integer found in the response
            import re
            match = re.search(r"\b(\d{1,3})\b", score_str)
            if match:
                score = int(match.group(1))
                if score > best_score:
                    best_score = score
                    best_user = potential_user
        except Exception as e:
            # If 402 error (insufficient credits), skip alchemy entirely
            if hasattr(e, 'status_code') and e.status_code == 402:
                logger.error("Skipping interest alchemy suggestion due to insufficient Mistral credits.")
                return None, None
            # Also check for Mistral APIStatusError with code 402 in message
            if '402' in str(e) and 'Insufficient credits' in str(e):
                logger.error("Skipping interest alchemy suggestion due to insufficient Mistral credits (string match).")
                return None, None
            logger.error(f"AI interest alchemy error for user {potential_user.id}: {str(e)}", exc_info=True)
            continue

    # Save the alchemy suggestion to UserSuggestion if found and if AI explanation is possible
    if best_user is not None:
        user_interests_set = set(i.name for i in getattr(user, 'interests', []).all()) if hasattr(user, 'interests') else set()
        best_user_interests_set = set(i.name for i in getattr(best_user, 'interests', []).all()) if hasattr(best_user, 'interests') else set()
        common_interests = list(user_interests_set.intersection(best_user_interests_set))
        location_score = 1.0 if getattr(user, 'location', None) and getattr(best_user, 'location', None) and getattr(user, 'location', '').lower() == getattr(best_user, 'location', '').lower() else 0.3
        education_score = 0.3
        explanation = None
        try:
            explanation = get_ai_match_explanation(user, best_user, common_interests, location_score, education_score, is_alchemy=True)
        except Exception as e:
            # If 402 error (insufficient credits), skip alchemy entirely
            if hasattr(e, 'status_code') and e.status_code == 402:
                logger.error("Skipping interest alchemy explanation due to insufficient Mistral credits.")
                return None, None
            if '402' in str(e) and 'Insufficient credits' in str(e):
                logger.error("Skipping interest alchemy explanation due to insufficient Mistral credits (string match).")
                return None, None
            logger.error(f"AI explanation error for interest alchemy: {str(e)}", exc_info=True)
            explanation = None
        if not explanation:
            try:
                minimal_prompt = f"Why would {user.username} and {best_user.username} be a good match?"
                response = client.chat.complete(
                    model=model,
                    messages=[{"role": "user", "content": minimal_prompt}]
                )
                explanation = response.choices[0].message.content.strip()
            except Exception as e:
                if hasattr(e, 'status_code') and e.status_code == 402:
                    logger.error("Skipping interest alchemy minimal explanation due to insufficient Mistral credits.")
                    return None, None
                if '402' in str(e) and 'Insufficient credits' in str(e):
                    logger.error("Skipping interest alchemy minimal explanation due to insufficient Mistral credits (string match).")
                    return None, None
                logger.error(f"Fallback AI explanation error: {str(e)}", exc_info=True)
                explanation = None
        if explanation:
            UserSuggestion.objects.update_or_create(
                user=user,
                suggested_user=best_user,
                defaults={
                    'score': best_score,
                    'is_active': True,
                    'match_highlights': [explanation],
                }
            )
            return best_user, best_score
        else:
            return None, None
    return None, None

def generate_traditional_suggestions(user, page=1, page_size=20, cache_hours=24):
    """
    Generate traditional user suggestions based on algorithmic factors only (no alchemy/AI).
    Caches results for cache_hours (default 24h).
    """
    try:
        if not user or not user.is_authenticated:
            logger.error("Invalid or unauthenticated user")
            return [], 0

        logger.info(f"Starting traditional suggestion generation for user: {user.username} (ID: {user.id}) - Page {page}")

        # Calculate offset for pagination
        offset = (page - 1) * page_size

        # Check for recent traditional suggestions (no match_highlights, not rejected, is_active)
        cutoff = timezone.now() - timedelta(hours=cache_hours)
        recent_suggestions = UserSuggestion.objects.filter(
            user=user,
            is_active=True,
            is_rejected=False,
            updated_at__gte=cutoff,
            match_highlights=[]
        ).order_by('-score')
        total_users = recent_suggestions.count()
        paginated_suggestions = list(recent_suggestions[offset:offset+page_size])
        if len(paginated_suggestions) == page_size:
            logger.info(f"[Traditional] Using cached suggestions for user {user.username} (ID: {user.id}) page {page}")
            return paginated_suggestions, total_users
        logger.info(f"[Traditional] Cache miss or not enough cached suggestions for user {user.username} (ID: {user.id}) page {page}, generating new suggestions.")
        # Get user's existing connections and requests with connection strength
        try:
            existing_connections = Connection.objects.filter(
                Q(user1=user) | Q(user2=user)
            ).values_list('user1_id', 'user2_id', 'connection_strength')
            logger.info(f"Found {len(existing_connections)} existing connections")
        except Exception as e:
            logger.error(f"Error fetching existing connections: {str(e)}", exc_info=True)
            existing_connections = []
        
        # Build connection strength map and get user's connections
        connection_strengths = {}
        user_connections = set()
        for u1, u2, strength in existing_connections:
            other_user = u2 if u1 == user.id else u1
            connection_strengths[other_user] = strength
            user_connections.add(other_user)
        
        # Get IDs of users we're already connected with
        connected_user_ids = user_connections.copy()
        # Add users from accepted connection requests
        try:
            accepted_requests = ConnectionRequest.objects.filter(
                (Q(sender=user) | Q(receiver=user)) & Q(status='accepted')
            ).values_list('sender_id', 'receiver_id')
            for s, r in accepted_requests:
                connected_user_ids.add(s)
                connected_user_ids.add(r)
            logger.info(f"Added {len(accepted_requests)} accepted connection requests to exclusion list")
        except Exception as e:
            logger.error(f"Error fetching accepted connections: {str(e)}", exc_info=True)
        # Get IDs of users we have pending requests with
        try:
            pending_requests = ConnectionRequest.objects.filter(
                (Q(sender=user) | Q(receiver=user)) & Q(status='pending')
            ).values_list('sender_id', 'receiver_id')
            logger.info(f"Found {len(pending_requests)} pending requests")
        except Exception as e:
            logger.error(f"Error fetching pending requests: {str(e)}", exc_info=True)
            pending_requests = []
        # Combine all excluded user IDs
        excluded_ids = connected_user_ids.union(set(s for s, r in pending_requests))
        # Get all potential users excluding connected and rejected
        try:
            potential_users = User.objects.exclude(
                id__in=excluded_ids
            ).exclude(
                id=user.id
            ).order_by('-last_login', 'id')
            total_users = potential_users.count()
            logger.info(f"Found {total_users} potential users for suggestions")
            if not potential_users.exists():
                logger.info(f"No potential users found for user {user.id}")
                return [], 0
        except Exception as e:
            logger.error(f"Error fetching potential users: {str(e)}", exc_info=True)
            return [], 0
        # Get user's interests
        user_interests = set()
        try:
            user_interests = set(interest.name for interest in user.interests.all())
            logger.info(f"User {user.id} has {len(user_interests)} interests: {user_interests}")
        except Exception as e:
            logger.warning(f"Could not get interests for user {user.id}: {str(e)}")
            user_interests = set()
        # Get potential users' interests and connections
        potential_user_data = {}
        for p_user in potential_users:
            try:
                # Get interests
                interests = set()
                try:
                    interests = set(interest.name for interest in p_user.interests.all())
                    logger.info(f"Potential user {p_user.id} has {len(interests)} interests: {interests}")
                except Exception as e:
                    logger.warning(f"Could not get interests for potential user {p_user.id}: {str(e)}")
                    interests = set()
                # Get user's connections
                p_user_connections = set()
                for u1, u2, _ in existing_connections:
                    if u1 == p_user.id:
                        p_user_connections.add(u2)
                    elif u2 == p_user.id:
                        p_user_connections.add(u1)
                potential_user_data[p_user.id] = {
                    'interests': interests,
                    'connections': p_user_connections
                }
            except Exception as e:
                logger.warning(f"Could not get data for potential user {p_user.id}: {str(e)}")
                potential_user_data[p_user.id] = {
                    'interests': set(),
                    'connections': set()
                }
        # Calculate scores and create suggestions
        suggestions_created = []
        for potential_user in potential_users:
            try:
                p_user_data = potential_user_data[potential_user.id]
                # Calculate common interests with detailed logging
                logger.info(f"\n=== Processing User {potential_user.username} ===")
                logger.info(f"Current user interests: {user_interests}")
                logger.info(f"Potential user interests: {p_user_data['interests']}")
                common_interests = list(user_interests.intersection(p_user_data['interests']))
                logger.info(f"Common interests found: {common_interests}")
                logger.info(f"Number of common interests: {len(common_interests)}")
                # Calculate mutual connections
                mutual_connections = len(user_connections.intersection(p_user_data['connections']))
                logger.info(f"Mutual connections: {mutual_connections}")
                # Calculate interest similarity using TF-IDF
                interest_score = 0
                for interest in common_interests:
                    score = calculate_tfidf_score(interest, [data['interests'] for data in potential_user_data.values()])
                    interest_score += score
                    logger.info(f"TF-IDF score for interest '{interest}': {score}")
                logger.info(f"Total interest score: {interest_score}")
                # Calculate network score
                network_score = calculate_network_score(user, potential_user, existing_connections)
                logger.info(f"Network score: {network_score}")
                # Calculate activity score
                activity_score = calculate_activity_score(user, potential_user)
                logger.info(f"Activity score: {activity_score}")
                # Calculate location score
                location_score = calculate_location_score(user, potential_user)
                logger.info(f"Location score: {location_score}")
                # Calculate education score
                education_score = calculate_education_score(user, potential_user)
                logger.info(f"Education score: {education_score}")
                # Calculate final score with updated weights
                final_score = (
                    interest_score * 0.25 +     # Interest similarity weight (reduced)
                    network_score * 0.25 +      # Network score weight (reduced)
                    activity_score * 0.15 +     # Activity score weight (reduced)
                    location_score * 0.20 +     # Location score weight (new)
                    education_score * 0.15      # Education score weight (new)
                )
                # Normalize score to 0-1 range and convert to percentage (0-100)
                final_score = round(min(max(final_score, 0), 1) * 100)
                logger.info(f"Final match score: {final_score}%")
                # --- AI explanation integration ---
                match_highlights = []
                # No AI explanation for traditional suggestions
                # Create or update the suggestion
                suggestion, created = UserSuggestion.objects.update_or_create(
                    user=user,
                    suggested_user=potential_user,
                    defaults={
                        'score': final_score,
                        'match_highlights': match_highlights,
                        'common_interests': common_interests,
                        'mutual_connections': mutual_connections,
                        'is_active': True
                    }
                )
                logger.info(f"Created suggestion for {potential_user.username}")
                logger.info(f"- Common interests: {len(common_interests)}")
                logger.info(f"- Location score: {location_score}")
                logger.info(f"- Education score: {education_score}")
                logger.info(f"- Final match score: {final_score}%")
                suggestions_created.append(suggestion)
            except Exception as e:
                logger.error(f"Error processing potential user {potential_user.id}: {str(e)}", exc_info=True)
                continue
        # Now apply pagination to suggestions_created (if needed)
        paginated_suggestions = suggestions_created[offset:offset+page_size]
        return paginated_suggestions, total_users
    except Exception as e:
        logger.error(f"Error in generate_traditional_suggestions: {str(e)}", exc_info=True)
        return [], 0

def generate_alchemy_suggestion(user, purpose_text=None):
    """
    Generate only the alchy friend suggestion using the AI logic.
    """
    if purpose_text is None:
        purpose_text = "find the most interesting connection"
    best_user, best_score = get_interest_alchemy_suggestion(user, purpose_text)
    if best_user is not None:
        try:
            alchemy_suggestion = UserSuggestion.objects.get(user=user, suggested_user=best_user, is_active=True)
            return alchemy_suggestion
        except UserSuggestion.DoesNotExist:
            return None
    return None

def get_batched_alchemy_scores(user, candidates, purpose_text, model="mistral-large-latest"):
    """
    Ask the AI to score up to 5 candidates for a user in a single prompt.
    Returns a list of (candidate, score) tuples.
    Uses Mistral AI model for all API calls.
    """
    client = get_mistral_client()
    if not client or not candidates:
        return []

    prompt = f"Main User:\n- Username: {user.username}\n- Interests: {', '.join(i.name for i in user.interests.all())}\n- Goals: {getattr(user, 'goals', '')}\n- Location: {getattr(user, 'location', '')}\n\nCandidates:\n"
    for idx, candidate in enumerate(candidates):
        prompt += (
            f"{idx+1}. {candidate.username} | Interests: {', '.join(i.name for i in candidate.interests.all())} | Goals: {getattr(candidate, 'goals', '')} | Location: {getattr(candidate, 'location', '')}\n"
        )
    prompt += (
        f"\nFor each candidate, score from 0-100 how strong a match they are for {user.username}'s goals and interests for the purpose: '{purpose_text}'. Respond with a list of {len(candidates)} numbers in order, separated by commas."
    )

    try:
        response = client.chat.complete(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        import re
        content = response.choices[0].message.content.strip()
        # Parse numbers from the response
        scores = [int(s) for s in re.findall(r'\b\d{1,3}\b', content)]
        results = list(zip(candidates, scores))
        return results
    except Exception as e:
        logger.error(f"Batched AI suggestion error: {str(e)}", exc_info=True)
        return []

def get_top_alchemy_suggestions(user, purpose_text, top_n=10, model="mistral-large-latest", cache_hours=24):
    """
    Use Mistral AI to find the top N best matches for a user based on a specific purpose/goal.
    Returns a list of UserSuggestion objects for the top N matches.
    Caches results for cache_hours (default 24h).
    Uses Mistral AI model for all API calls.
    """
    # Check for recent suggestions
    cutoff = timezone.now() - timedelta(hours=cache_hours)
    recent_suggestions = UserSuggestion.objects.filter(
        user=user,
        is_active=True,
        updated_at__gte=cutoff
    ).order_by('-score')[:top_n]
    if recent_suggestions.count() == top_n:
        logger.info(f"[Alchemy] Using cached top {top_n} suggestions for user {user.username} (ID: {user.id})")
        return list(recent_suggestions)
    logger.info(f"[Alchemy] Cache miss or not enough cached suggestions for user {user.username} (ID: {user.id}), generating new suggestions.")

    # Exclude self and already connected users
    try:
        existing_connections = Connection.objects.filter(
            Q(user1=user) | Q(user2=user)
        ).values_list('user1_id', 'user2_id')
        connected_user_ids = set()
        for u1, u2 in existing_connections:
            other_user = u2 if u1 == user.id else u1
            connected_user_ids.add(other_user)
        connected_user_ids.add(user.id)
    except Exception as e:
        logger.error(f"Error fetching existing connections: {str(e)}", exc_info=True)
        connected_user_ids = {user.id}

    potential_users = list(User.objects.exclude(id__in=connected_user_ids))
    if not potential_users:
        return []

    # Batch in groups of 5 for efficiency
    all_scores = []
    for i in range(0, len(potential_users), 5):
        batch = potential_users[i:i+5]
        results = get_batched_alchemy_scores(user, batch, purpose_text, model="mistral-large-latest")
        all_scores.extend(results)

    # Sort by score descending and take top N
    all_scores = [(candidate, score) for candidate, score in all_scores if isinstance(score, int)]
    all_scores.sort(key=lambda x: x[1], reverse=True)
    top_matches = all_scores[:top_n]

    # Save these suggestions to UserSuggestion
    suggestions = []
    for candidate, score in top_matches:
        suggestion, _ = UserSuggestion.objects.update_or_create(
            user=user,
            suggested_user=candidate,
            defaults={
                'score': score,
                'is_active': True,
                'match_highlights': [],
            }
        )
        suggestions.append(suggestion)
    return suggestions
