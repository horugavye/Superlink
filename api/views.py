from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from users.models import (
    User, UserSocialProfile, UserAnalytics, UserBadge,
    UserCertification, UserProject, Skill, UserEndorsement,
    UserBlock, PersonalityTag, Language, UserAvailability,
    Education, WorkExperience, Achievement, UserInterest,
    UserFollowing
)
from .serializers import (
    UserSerializer, UserProfileSerializer, UserSocialProfileSerializer,
    UserAnalyticsSerializer, UserBadgeSerializer, UserCertificationSerializer,
    UserProjectSerializer, SkillSerializer, UserEndorsementSerializer,
    PersonalityTagSerializer, LanguageSerializer, UserAvailabilitySerializer,
    EducationSerializer, WorkExperienceSerializer, AchievementSerializer,
    UserInterestSerializer
)
from rest_framework import viewsets
import logging
from django.utils import timezone
from django.db import models

logger = logging.getLogger(__name__)

@csrf_exempt
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user(request):
    serializer = UserProfileSerializer(request.user, context={'request': request})
    return Response(serializer.data)

@csrf_exempt
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_profile(request):
    serializer = UserProfileSerializer(request.user, context={'request': request})
    return Response(serializer.data)

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def get_public_profile(request, username):
    user = get_object_or_404(User, username=username)
    serializer = UserProfileSerializer(user)
    data = serializer.data
    # Always include a 'private' flag
    data['private'] = (user.profile_visibility == 'private')
    return Response(data)

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def search_profiles(request):
    query = request.query_params.get('q', '')
    if not query:
        return Response({'error': 'Search query is required'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    users = User.objects.filter(
        username__icontains=query
    ) | User.objects.filter(
        first_name__icontains=query
    ) | User.objects.filter(
        last_name__icontains=query
    )
    
    if not request.user.is_authenticated:
        users = users.filter(profile_visibility='public')
    elif request.user.is_authenticated:
        users = users.exclude(profile_visibility='private')
    
    serializer = UserProfileSerializer(users, many=True)
    return Response(serializer.data)

@csrf_exempt
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    # Allow users to change their username and other fields
    # Remove the check that blocks username changes

    # Handle image deletion
    if 'avatar' in request.data and request.data['avatar'] == '':
        if request.user.avatar:
            request.user.avatar.delete()  # This will delete the file from storage
        request.user.avatar = None
        request.user.save()
    
    if 'cover_photo' in request.data and request.data['cover_photo'] == '':
        if request.user.cover_photo:
            request.user.cover_photo.delete()  # This will delete the file from storage
        request.user.cover_photo = None
        request.user.save()

    serializer = UserProfileSerializer(request.user, data=request.data, partial=True, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def social_profile(request):
    profile, created = UserSocialProfile.objects.get_or_create(user=request.user)
    if request.method == 'GET':
        serializer = UserSocialProfileSerializer(profile)
        return Response(serializer.data)
    else:
        serializer = UserSocialProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def skills(request):
    if request.method == 'GET':
        skills = Skill.objects.filter(user=request.user)
        serializer = SkillSerializer(skills, many=True)
        return Response(serializer.data)
    else:
        serializer = SkillSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_skill(request, skill_id):
    skill = get_object_or_404(Skill, id=skill_id, user=request.user)
    skill.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

@csrf_exempt
@api_view(['GET', 'POST', 'PATCH'])
@permission_classes([IsAuthenticated])
def certifications(request, cert_id=None):
    if request.method == 'GET':
        certs = UserCertification.objects.filter(user=request.user)
        serializer = UserCertificationSerializer(certs, many=True)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = UserCertificationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    elif request.method == 'PATCH':
        if not cert_id:
            return Response({'error': 'Certification ID is required for PATCH'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        try:
            certification = UserCertification.objects.get(id=cert_id, user=request.user)
            serializer = UserCertificationSerializer(certification, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except UserCertification.DoesNotExist:
            return Response({'error': 'Certification not found'}, 
                          status=status.HTTP_404_NOT_FOUND)

@csrf_exempt
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_certification(request, cert_id):
    certification = get_object_or_404(UserCertification, id=cert_id, user=request.user)
    certification.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def projects(request):
    if request.method == 'GET':
        projects = UserProject.objects.filter(user=request.user)
        serializer = UserProjectSerializer(projects, many=True)
        return Response(serializer.data)
    else:
        serializer = UserProjectSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_project(request, project_id):
    project = get_object_or_404(UserProject, id=project_id, user=request.user)
    project.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

@csrf_exempt
@api_view(['GET', 'POST', 'PATCH'])
@permission_classes([IsAuthenticated])
def work_experience(request, experience_id=None):
    if request.method == 'GET':
        username = request.query_params.get('username')
        if username and username != request.user.username:
            try:
                user = User.objects.get(username=username)
                experiences = WorkExperience.objects.filter(user=user)
                serializer = WorkExperienceSerializer(experiences, many=True)
                return Response(serializer.data)
            except User.DoesNotExist:
                return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        else:
            # Viewing own profile
            if experience_id:
                try:
                    experience = WorkExperience.objects.get(id=experience_id, user=request.user)
                    serializer = WorkExperienceSerializer(experience)
                    return Response(serializer.data)
                except WorkExperience.DoesNotExist:
                    return Response({'error': 'Experience not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                experiences = WorkExperience.objects.filter(user=request.user)
                serializer = WorkExperienceSerializer(experiences, many=True)
                return Response(serializer.data)
    
    elif request.method == 'POST':
        # Only allow creating experience for own profile
        data = request.data.copy()
        data['user'] = request.user.id
        serializer = WorkExperienceSerializer(data=data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'PATCH':
        if not experience_id:
            return Response({'error': 'Experience ID is required for PATCH'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            # Only allow updating own experience
            experience = WorkExperience.objects.get(id=experience_id, user=request.user)
            serializer = WorkExperienceSerializer(experience, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except WorkExperience.DoesNotExist:
            return Response({'error': 'Experience not found or you do not have permission to modify it'}, 
                          status=status.HTTP_404_NOT_FOUND)

@csrf_exempt
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_work_experience(request, experience_id):
    try:
        # Only allow deleting own experience
        experience = WorkExperience.objects.get(id=experience_id, user=request.user)
        experience.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    except WorkExperience.DoesNotExist:
        return Response({'error': 'Experience not found or you do not have permission to delete it'}, 
                       status=status.HTTP_404_NOT_FOUND)

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    """
    Register a new user. Required fields: username, email, password, password2, first_name, last_name, bio, location, personality_tags (list), interests (list)
    """
    serializer = UserSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': serializer.data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'redirect_url': '/connectionrequests?suggested=1',
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def login_user(request):
    try:
        email = request.data.get('email')
        password = request.data.get('password')
        
        logger.info(f"Login attempt for email: {email}")
        logger.debug(f"Request data: {request.data}")
        logger.debug(f"Request headers: {request.headers}")
        
        if not email or not password:
            logger.warning("Login attempt failed: Missing email or password")
            return Response({'error': 'Please provide both email and password'}, 
                           status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email)
            username = user.username
            logger.info(f"Found user with username: {username}")
        except User.DoesNotExist:
            logger.warning(f"No user found with email: {email}")
            return Response({'error': 'Invalid credentials'}, 
                           status=status.HTTP_401_UNAUTHORIZED)
        
        user = authenticate(username=username, password=password)
        
        if user:
            if not user.is_active:
                logger.warning(f"Login attempt for inactive user: {username}")
                return Response({'error': 'Account is inactive'}, 
                               status=status.HTTP_401_UNAUTHORIZED)
                
            logger.info(f"User authenticated successfully: {username}")
            refresh = RefreshToken.for_user(user)
            serializer = UserSerializer(user)
            
            # Update last login
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            
            return Response({
                'user': serializer.data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            })
        
        logger.warning(f"Authentication failed for user: {username}")
        return Response({'error': 'Invalid credentials'}, 
                       status=status.HTTP_401_UNAUTHORIZED)
    except Exception as e:
        logger.error(f"Unexpected error during login: {str(e)}", exc_info=True)
        logger.error(f"Request data: {request.data}")
        logger.error(f"Request headers: {request.headers}")
        return Response(
            {'error': 'An unexpected error occurred during login'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_token(request):
    try:
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'error': 'Refresh token is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Check if the server is shutting down
            if getattr(request, '_server_shutdown', False):
                return Response(
                    {'error': 'Server is shutting down. Please try again later.'}, 
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
            
            refresh = RefreshToken(refresh_token)
            return Response({
                'access': str(refresh.access_token),
            })
        except Exception as e:
            logger.error(f"Token refresh failed: {str(e)}")
            return Response(
                {'error': 'Invalid or expired refresh token'}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
    except Exception as e:
        logger.error(f"Unexpected error during token refresh: {str(e)}")
        return Response(
            {'error': 'An unexpected error occurred'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# Endorsements Endpoints
@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def endorsements(request):
    if request.method == 'GET':
        endorsements = UserEndorsement.objects.filter(user=request.user)
        serializer = UserEndorsementSerializer(endorsements, many=True)
        return Response(serializer.data)
    else:
        serializer = UserEndorsementSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_endorsement(request, endorsement_id):
    endorsement = get_object_or_404(UserEndorsement, id=endorsement_id, user=request.user)
    endorsement.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

# Personality Tags Endpoints
@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def personality_tags(request):
    if request.method == 'GET':
        tags = PersonalityTag.objects.all()
        serializer = PersonalityTagSerializer(tags, many=True)
        return Response(serializer.data)
    else:
        tag_name = request.data.get('name')
        tag_color = request.data.get('color')
        tag, created = PersonalityTag.objects.get_or_create(
            name=tag_name,
            defaults={'color': tag_color}
        )
        if not created and tag_color:
            tag.color = tag_color
            tag.save()
        request.user.personality_tags.add(tag)
        serializer = PersonalityTagSerializer(tag)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

@csrf_exempt
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_personality_tag(request, tag_id):
    tag = get_object_or_404(PersonalityTag, id=tag_id)
    request.user.personality_tags.remove(tag)
    return Response(status=status.HTTP_204_NO_CONTENT)

@csrf_exempt
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_personality_tag_from_db(request, tag_id):
    tag = get_object_or_404(PersonalityTag, id=tag_id)
    tag.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

@csrf_exempt
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_personality_tags(request):
    tags = request.user.personality_tags.all()
    serializer = PersonalityTagSerializer(tags, many=True)
    return Response(serializer.data)

# Languages Endpoints
@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def languages(request):
    if request.method == 'GET':
        languages = Language.objects.filter(user=request.user)
        serializer = LanguageSerializer(languages, many=True)
        return Response(serializer.data)
    else:
        serializer = LanguageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_language(request, language_id):
    language = get_object_or_404(Language, id=language_id, user=request.user)
    language.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

# Availability Endpoints
@csrf_exempt
@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def availability(request):
    availability, created = UserAvailability.objects.get_or_create(user=request.user)
    if request.method == 'GET':
        serializer = UserAvailabilitySerializer(availability)
        return Response(serializer.data)
    else:
        serializer = UserAvailabilitySerializer(availability, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# Achievements Endpoints
@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def achievements(request):
    if request.method == 'GET':
        achievements = Achievement.objects.filter(user=request.user)
        serializer = AchievementSerializer(achievements, many=True)
        return Response(serializer.data)
    else:
        serializer = AchievementSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def achievement_detail(request, achievement_id):
    achievement = get_object_or_404(Achievement, id=achievement_id, user=request.user)
    
    if request.method == 'PATCH':
        serializer = AchievementSerializer(achievement, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    elif request.method == 'DELETE':
        achievement.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# Interests Endpoints
@csrf_exempt
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def available_interests(request):
    """Get all available interests in the system"""
    interests = UserInterest.objects.values('name').distinct()
    return Response([interest['name'] for interest in interests])

@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def interests(request):
    if request.method == 'GET':
        interests = UserInterest.objects.filter(user=request.user)
        serializer = UserInterestSerializer(interests, many=True)
        return Response(serializer.data)
    else:
        try:
            # Debug prints
            print("Request body:", request.body)
            print("Request POST:", request.POST)
            print("Request data:", request.data)
            print("Content type:", request.content_type)
            
            # Ensure we have the name field
            if not request.data or 'name' not in request.data:
                return Response(
                    {'error': 'name field is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            name = request.data.get('name', '').strip()
            if not name:
                return Response(
                    {'error': 'name cannot be empty'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if interest already exists for this user
            existing_interest = UserInterest.objects.filter(
                user=request.user,
                name__iexact=name
            ).first()
            
            if existing_interest:
                serializer = UserInterestSerializer(existing_interest)
                return Response(serializer.data)
            
            # Create new interest
            try:
                interest = UserInterest.objects.create(
                    user=request.user,
                    name=name
                )
                serializer = UserInterestSerializer(interest)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except Exception as e:
                print(f"Error creating interest: {str(e)}")
                return Response(
                    {'error': f'Failed to create interest: {str(e)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            print(f"Unexpected error in interests view: {str(e)}")
            return Response(
                {'error': f'An unexpected error occurred: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

@csrf_exempt
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_interest(request, interest_id):
    interest = get_object_or_404(UserInterest, id=interest_id, user=request.user)
    interest.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

# Following/Followers Endpoints
@csrf_exempt
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def followers(request):
    followers = UserFollowing.objects.filter(following_user=request.user)
    serializer = UserSerializer([f.user for f in followers], many=True)
    return Response(serializer.data)

@csrf_exempt
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def following(request):
    following = UserFollowing.objects.filter(user=request.user)
    serializer = UserSerializer([f.following_user for f in following], many=True)
    return Response(serializer.data)

@csrf_exempt
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def follow_user(request, username):
    user_to_follow = get_object_or_404(User, username=username)
    if user_to_follow == request.user:
        return Response(
            {'error': 'You cannot follow yourself'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    UserFollowing.objects.get_or_create(
        user=request.user,
        following_user=user_to_follow
    )
    return Response(status=status.HTTP_201_CREATED)

@csrf_exempt
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def unfollow_user(request, username):
    user_to_unfollow = get_object_or_404(User, username=username)
    UserFollowing.objects.filter(
        user=request.user,
        following_user=user_to_unfollow
    ).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def education(request):
    if request.method == 'GET':
        educations = Education.objects.filter(user=request.user)
        serializer = EducationSerializer(educations, many=True)
        return Response(serializer.data)
    else:
        serializer = EducationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_education(request, education_id):
    education = get_object_or_404(Education, id=education_id, user=request.user)
    serializer = EducationSerializer(education, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_education(request, education_id):
    education = get_object_or_404(Education, id=education_id, user=request.user)
    education.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

# Online Status Endpoints
@csrf_exempt
@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def online_status(request):
    """
    Get or update the current user's online status.
    GET: Returns current online status and last_active
    PUT: Updates online status (online, away, offline, busy)
    """
    if request.method == 'GET':
        return Response({
            'online_status': request.user.online_status,
            'last_active': request.user.last_active,
            'is_online': request.user.online_status == 'online'
        })
    else:
        new_status = request.data.get('online_status')
        if new_status not in ['online', 'away', 'offline', 'busy']:
            return Response(
                {'error': 'Invalid status. Must be one of: online, away, offline, busy'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        request.user.online_status = new_status
        request.user.save(update_fields=['online_status'])
        
        return Response({
            'online_status': request.user.online_status,
            'last_active': request.user.last_active,
            'is_online': request.user.online_status == 'online'
        })

@csrf_exempt
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_online_status(request, user_id):
    """
    Get online status of a specific user.
    Only works for connected users or public profiles.
    """
    try:
        target_user = User.objects.get(id=user_id)
        
        # Check if user is viewing their own status
        if target_user == request.user:
            return Response({
                'online_status': target_user.online_status,
                'last_active': target_user.last_active,
                'is_online': target_user.online_status == 'online'
            })
        
        # Check if users are connected
        from connections.models import Connection
        is_connected = Connection.objects.filter(
            (models.Q(user1=request.user, user2=target_user) | 
             models.Q(user1=target_user, user2=request.user)),
            is_active=True
        ).exists()
        
        # Check if target user's profile is public
        is_public = target_user.profile_visibility == 'public'
        
        if not is_connected and not is_public:
            return Response(
                {'error': 'Cannot view status of this user'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        return Response({
            'online_status': target_user.online_status,
            'last_active': target_user.last_active,
            'is_online': target_user.online_status == 'online'
        })
        
    except User.DoesNotExist:
        return Response(
            {'error': 'User not found'},
            status=status.HTTP_404_NOT_FOUND
        )

@csrf_exempt
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def online_users(request):
    """
    Get list of online users (connected users and public profiles).
    """
    # Get connected users
    from connections.models import Connection
    connected_users = Connection.objects.filter(
        (models.Q(user1=request.user) | models.Q(user2=request.user)),
        is_active=True
    ).values_list('user1', 'user2')
    
    # Flatten the list
    connected_user_ids = set()
    for user1, user2 in connected_users:
        connected_user_ids.add(user1)
        connected_user_ids.add(user2)
    
    # Get public users who are online
    public_online_users = User.objects.filter(
        profile_visibility='public',
        online_status='online'
    ).exclude(id=request.user.id)
    
    # Get connected users who are online
    connected_online_users = User.objects.filter(
        id__in=connected_user_ids,
        online_status='online'
    ).exclude(id=request.user.id)
    
    # Combine and serialize
    all_online_users = list(public_online_users) + list(connected_online_users)
    
    # Remove duplicates
    seen_ids = set()
    unique_users = []
    for user in all_online_users:
        if user.id not in seen_ids:
            seen_ids.add(user.id)
            unique_users.append(user)
    
    serializer = UserSerializer(unique_users, many=True, context={'request': request})
    return Response(serializer.data)

@csrf_exempt
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    user = request.user
    current_password = request.data.get('current_password')
    new_password = request.data.get('new_password')
    confirm_new_password = request.data.get('confirm_new_password')

    if not current_password or not new_password or not confirm_new_password:
        return Response({'error': 'All password fields are required.'}, status=status.HTTP_400_BAD_REQUEST)

    if not user.check_password(current_password):
        return Response({'error': 'Current password is incorrect.'}, status=status.HTTP_400_BAD_REQUEST)

    if new_password != confirm_new_password:
        return Response({'error': 'New passwords do not match.'}, status=status.HTTP_400_BAD_REQUEST)

    if current_password == new_password:
        return Response({'error': 'New password must be different from the current password.'}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new_password)
    user.save()
    return Response({'message': 'Password changed successfully.'}, status=status.HTTP_200_OK)
