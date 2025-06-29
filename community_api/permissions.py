from rest_framework import permissions

class IsCommunityMember(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        # Check if user is a member of the community
        return obj.members.filter(user=request.user).exists()

class IsCommunityAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        # Check if user is an admin of the community
        return obj.members.filter(user=request.user, role='admin').exists()

class IsCommunityModerator(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        # Check if user is a moderator or admin of the community
        return obj.members.filter(
            user=request.user,
            role__in=['admin', 'moderator']
        ).exists()

class IsPostAuthor(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        # Check if user is the author of the post
        return obj.author == request.user

class IsCommentAuthor(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        # Check if user is the author of the comment
        return obj.author == request.user

class IsEventCreator(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        # Check if user is the creator of the event
        return obj.created_by == request.user

class CanManageEvent(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        # Check if user is the event creator or a community admin/moderator
        return (obj.created_by == request.user or 
                obj.community.members.filter(
                    user=request.user,
                    role__in=['admin', 'moderator']
                ).exists())

class IsReplyAuthor(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        # Check if user is the author of the reply
        return obj.author == request.user 