from django.urls import path
from django.urls import include
from . import views
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.routers import DefaultRouter

urlpatterns = [
    path('auth/user/', views.get_user, name='user'),
    path('auth/profile/', views.get_profile, name='profile'),
    path('auth/profile/update/', views.update_profile, name='update_profile'),
    path('auth/profile/<str:username>/', views.get_public_profile, name='public_profile'),
    path('auth/profiles/search/', views.search_profiles, name='search_profiles'),
    path('auth/register/', views.register_user, name='register'),
    path('auth/login/', views.login_user, name='login'),
    path('auth/token/refresh/', views.refresh_token, name='token_refresh'),
    path('auth/social-profile/', views.social_profile, name='social_profile'),
    path('auth/skills/', views.skills, name='skills'),
    path('auth/skills/<int:skill_id>/', views.delete_skill, name='delete_skill'),
    path('auth/certifications/', views.certifications, name='certifications'),
    path('auth/certifications/<str:cert_id>/', views.certifications, name='certification_detail'),
    path('auth/certifications/<str:cert_id>/delete/', views.delete_certification, name='delete_certification'),
    path('auth/projects/', views.projects, name='projects'),
    path('auth/projects/<int:project_id>/', views.delete_project, name='delete_project'),
    path('auth/education/', views.education, name='education'),
    path('auth/education/<int:education_id>/', views.update_education, name='update_education'),
    path('auth/education/<int:education_id>/delete/', views.delete_education, name='delete_education'),
    path('auth/work-experience/', views.work_experience, name='work_experience'),
    path('auth/work-experience/<int:experience_id>/', views.work_experience, name='work_experience_detail'),
    path('auth/work-experience/<int:experience_id>/delete/', views.delete_work_experience, name='delete_work_experience'),
    path('auth/endorsements/', views.endorsements, name='endorsements'),
    path('auth/endorsements/<int:endorsement_id>/', views.delete_endorsement, name='delete_endorsement'),
    path('auth/personality-tags/', views.personality_tags, name='personality_tags'),
    path('auth/personality-tags/<int:tag_id>/', views.delete_personality_tag, name='delete_personality_tag'),
    path('auth/personality-tags/<int:tag_id>/delete/', views.delete_personality_tag_from_db, name='delete_personality_tag_from_db'),
    path('auth/user/personality-tags/', views.user_personality_tags, name='user_personality_tags'),
    path('auth/languages/', views.languages, name='languages'),
    path('auth/languages/<int:language_id>/', views.delete_language, name='delete_language'),
    path('auth/availability/', views.availability, name='availability'),
    path('auth/achievements/', views.achievements, name='achievements'),
    path('auth/achievements/<int:achievement_id>/', views.achievement_detail, name='achievement_detail'),
    path('auth/interests/', views.interests, name='interests'),
    path('auth/interests/<int:interest_id>/', views.delete_interest, name='delete_interest'),
    path('auth/available-interests/', views.available_interests, name='available_interests'),
    path('auth/followers/', views.followers, name='followers'),
    path('auth/following/', views.following, name='following'),
    path('auth/follow/<str:username>/', views.follow_user, name='follow_user'),
    path('auth/unfollow/<str:username>/', views.unfollow_user, name='unfollow_user'),
    
    # Online Status Endpoints
    path('auth/online-status/', views.online_status, name='online_status'),
    path('auth/online-status/<int:user_id>/', views.user_online_status, name='user_online_status'),
    path('auth/online-users/', views.online_users, name='online_users'),
    path('connections/', include('connections.urls')),
    path('auth/change-password/', views.change_password, name='change_password'),
]

router = DefaultRouter()
urlpatterns += router.urls 