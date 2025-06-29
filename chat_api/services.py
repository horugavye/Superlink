import logging
import json
from typing import List, Dict, Any, Optional
from django.utils import timezone
from django.db.models import Q
from django.conf import settings
from chat.models import Conversation, Message, User

logger = logging.getLogger(__name__)

# Initialize Mistral AI client
try:
    from mistralai import Mistral
    import os
    
    # Mistral configuration
    mistral_api_key = "4Q6ICI5AWFuwfuD5bu4cpPTWOKRbyDEY"
    mistral_model = "mistral-large-latest"
    
    logger.info(f"Mistral configuration - Model: {mistral_model}")
    logger.info(f"Mistral API key configured: {'Yes' if mistral_api_key and mistral_api_key != 'your_mistral_key_here' else 'No'}")
    
    if mistral_api_key and mistral_api_key != "your_mistral_key_here":
        try:
            # Set up Mistral client
            mistral_client = Mistral(api_key=mistral_api_key)
            MISTRAL_AVAILABLE = True
            logger.info("Mistral AI API client successfully initialized")
        except Exception as e:
            MISTRAL_AVAILABLE = False
            mistral_client = None
            logger.error(f"Failed to initialize Mistral AI API client: {str(e)}")
    else:
        MISTRAL_AVAILABLE = False
        mistral_client = None
        logger.warning("Mistral API key not configured.")
        
except ImportError as e:
    MISTRAL_AVAILABLE = False
    mistral_client = None
    logger.error(f"Mistral library not installed: {str(e)}")
except Exception as e:
    MISTRAL_AVAILABLE = False
    mistral_client = None
    logger.error(f"Unexpected error initializing Mistral API: {str(e)}")

class RealTimeSuggestionService:
    """Service for generating real-time AI-powered message suggestions without saving to database."""
    
    @staticmethod
    def generate_suggestions(
        conversation: Conversation,
        user: User,
        suggestion_types: List[str] = None,
        max_suggestions: int = 3,
        custom_prompt: str = None
    ) -> List[Dict[str, Any]]:
        """
        Generate real-time AI-powered message suggestions for a user in a conversation.
        
        Args:
            conversation: The conversation to generate suggestions for
            user: The user requesting suggestions
            suggestion_types: Types of suggestions to generate
            max_suggestions: Maximum number of suggestions to generate
            custom_prompt: Custom prompt from user for specific suggestions
            
        Returns:
            List of suggestion dictionaries (not saved to database)
        """
        try:
            # Get conversation context with enhanced user knowledge
            context = RealTimeSuggestionService._build_conversation_context(conversation, user)
            
            # Generate suggestions using AI
            ai_suggestions = RealTimeSuggestionService._generate_ai_suggestions(
                context, suggestion_types, max_suggestions, custom_prompt
            )
            
            # Convert to response format (no database objects)
            suggestions = []
            for i, suggestion_data in enumerate(ai_suggestions):
                suggestion = {
                    'id': f"temp_{i}_{int(timezone.now().timestamp())}",  # Temporary ID
                    'conversation_id': conversation.id,
                    'user_id': user.id,
                    'suggestion_type': suggestion_data['type'],
                    'content': suggestion_data['content'],
                    'context': suggestion_data['context'],
                    'confidence_score': suggestion_data['confidence'],
                    'created_at': timezone.now().isoformat(),
                    'is_real_time': True
                }
                suggestions.append(suggestion)
            
            logger.info(f"Generated {len(suggestions)} real-time suggestions for user {user.id} in conversation {conversation.id}")
            return suggestions
            
        except Exception as e:
            logger.error(f"Error generating real-time suggestions: {str(e)}", exc_info=True)
            return []
    
    @staticmethod
    def _build_conversation_context(conversation: Conversation, user: User) -> Dict[str, Any]:
        """Build context for AI suggestion generation with comprehensive user knowledge."""
        # Get recent messages (last 20 messages)
        recent_messages = conversation.messages.all().order_by('-created_at')[:20]
        
        # Get conversation participants
        participants = conversation.get_participants()
        
        # Build enhanced context with user knowledge
        context = {
            'conversation_type': conversation.type,
            'conversation_name': conversation.name or 'Direct Message',
            'participants': RealTimeSuggestionService._get_enhanced_participant_data(participants, user),
            'recent_messages': [
                {
                    'id': msg.id,
                    'content': msg.content,
                    'sender': {
                        'id': msg.sender.id,
                        'username': msg.sender.username,
                        'is_current_user': msg.sender.id == user.id
                    },
                    'message_type': msg.message_type,
                    'created_at': msg.created_at.isoformat(),
                    'is_reply': bool(msg.reply_to),
                    'has_files': msg.files.exists()
                }
                for msg in recent_messages
            ],
            'current_user': RealTimeSuggestionService._get_enhanced_user_data(user),
            'other_participants': RealTimeSuggestionService._get_enhanced_user_data(
                [p for p in participants if p.id != user.id][0] if len(participants) > 1 else None
            ) if len(participants) > 1 else None
        }
        
        # Debug logging
        logger.info(f"Built conversation context for user {user.username} (ID: {user.id})")
        logger.info(f"Conversation: {conversation.name} (ID: {conversation.id})")
        logger.info(f"Recent messages count: {len(context['recent_messages'])}")
        
        # Log message ownership
        for i, msg in enumerate(context['recent_messages'][:5]):  # Log first 5 messages
            logger.info(f"Message {i+1}: {msg['sender']['username']} (is_current_user: {msg['sender']['is_current_user']}): {msg['content'][:50]}...")
        
        return context
    
    @staticmethod
    def _get_enhanced_participant_data(participants: List[User], current_user: User) -> List[Dict[str, Any]]:
        """Get enhanced participant data including personality, interests, posts, etc."""
        enhanced_participants = []
        
        for participant in participants:
            try:
                # Get personality tags
                personality_tags = []
                try:
                    personality_tags = [
                        {'name': tag.name, 'color': tag.color}
                        for tag in participant.personality_tags.all()
                    ]
                except Exception as e:
                    logger.warning(f"Error getting personality tags for user {participant.id}: {str(e)}")
                
                # Get interests
                interests = []
                try:
                    interests = [
                        {'name': interest.name}
                        for interest in participant.interests.all()
                    ]
                except Exception as e:
                    logger.warning(f"Error getting interests for user {participant.id}: {str(e)}")
                
                # Get recent posts
                recent_posts = []
                try:
                    from community.models import PersonalPost, CommunityPost
                    personal_posts = PersonalPost.objects.filter(
                        author=participant,
                        visibility__in=['personal_connections', 'personal_public']
                    ).order_by('-created_at')[:3]
                    
                    community_posts = CommunityPost.objects.filter(
                        author=participant,
                        visibility='community'
                    ).order_by('-created_at')[:3]
                    
                    for post in list(personal_posts) + list(community_posts):
                        recent_posts.append({
                            'id': post.id,
                            'title': post.title,
                            'content': post.content[:200] + '...' if len(post.content) > 200 else post.content,
                            'created_at': post.created_at.isoformat(),
                            'rating': float(post.rating),
                            'comment_count': post.comment_count,
                            'type': 'personal' if hasattr(post, 'personal_post') else 'community'
                        })
                except Exception as e:
                    logger.warning(f"Error getting posts for user {participant.id}: {str(e)}")
                
                # Get skills
                skills = []
                try:
                    skills = [
                        {'name': skill.name, 'level': skill.level}
                        for skill in participant.skills.all()
                    ]
                except Exception as e:
                    logger.warning(f"Error getting skills for user {participant.id}: {str(e)}")
                
                # Get work experience
                work_experience = []
                try:
                    work_experience = [
                        {
                            'company': exp.company,
                            'role': exp.role,
                            'duration': exp.duration,
                            'highlights': exp.highlights[:3] if exp.highlights else []
                        }
                        for exp in participant.work_experience.all()[:2]
                    ]
                except Exception as e:
                    logger.warning(f"Error getting work experience for user {participant.id}: {str(e)}")
                
                # Get education
                education = []
                try:
                    education = [
                        {
                            'school': edu.school,
                            'degree': edu.degree,
                            'field': edu.field,
                            'year': edu.year
                        }
                        for edu in participant.education.all()[:2]
                    ]
                except Exception as e:
                    logger.warning(f"Error getting education for user {participant.id}: {str(e)}")
                
                enhanced_participants.append({
                    'id': participant.id,
                    'username': participant.username,
                    'first_name': participant.first_name,
                    'last_name': participant.last_name,
                    'is_current_user': participant.id == current_user.id,
                    'bio': getattr(participant, 'bio', ''),
                    'location': getattr(participant, 'location', ''),
                    'personality_tags': personality_tags,
                    'interests': interests,
                    'skills': skills,
                    'work_experience': work_experience,
                    'education': education,
                    'recent_posts': recent_posts
                })
                
            except Exception as e:
                logger.error(f"Error building enhanced data for participant {participant.id}: {str(e)}")
                # Fallback to basic data
                enhanced_participants.append({
                    'id': participant.id,
                    'username': participant.username,
                    'first_name': participant.first_name,
                    'last_name': participant.last_name,
                    'is_current_user': participant.id == current_user.id
                })
        
        return enhanced_participants
    
    @staticmethod
    def _get_enhanced_user_data(user: User) -> Dict[str, Any]:
        """Get enhanced data for a single user."""
        if not user:
            return {}
        
        try:
            # Get personality tags
            personality_tags = []
            try:
                personality_tags = [
                    {'name': tag.name, 'color': tag.color}
                    for tag in user.personality_tags.all()
                ]
            except Exception as e:
                logger.warning(f"Error getting personality tags for user {user.id}: {str(e)}")
            
            # Get interests
            interests = []
            try:
                interests = [
                    {'name': interest.name}
                    for interest in user.interests.all()
                ]
            except Exception as e:
                logger.warning(f"Error getting interests for user {user.id}: {str(e)}")
            
            # Get recent posts
            recent_posts = []
            try:
                from community.models import PersonalPost, CommunityPost
                personal_posts = PersonalPost.objects.filter(
                    author=user,
                    visibility__in=['personal_connections', 'personal_public']
                ).order_by('-created_at')[:3]
                
                community_posts = CommunityPost.objects.filter(
                    author=user,
                    visibility='community'
                ).order_by('-created_at')[:3]
                
                for post in list(personal_posts) + list(community_posts):
                    recent_posts.append({
                        'id': post.id,
                        'title': post.title,
                        'content': post.content[:200] + '...' if len(post.content) > 200 else post.content,
                        'created_at': post.created_at.isoformat(),
                        'rating': float(post.rating),
                        'comment_count': post.comment_count,
                        'type': 'personal' if hasattr(post, 'personal_post') else 'community'
                    })
            except Exception as e:
                logger.warning(f"Error getting posts for user {user.id}: {str(e)}")
            
            # Get skills
            skills = []
            try:
                skills = [
                    {'name': skill.name, 'level': skill.level}
                    for skill in user.skills.all()
                ]
            except Exception as e:
                logger.warning(f"Error getting skills for user {user.id}: {str(e)}")
            
            # Get work experience
            work_experience = []
            try:
                work_experience = [
                    {
                        'company': exp.company,
                        'role': exp.role,
                        'duration': exp.duration,
                        'highlights': exp.highlights[:3] if exp.highlights else []
                    }
                    for exp in user.work_experience.all()[:2]
                ]
            except Exception as e:
                logger.warning(f"Error getting work experience for user {user.id}: {str(e)}")
            
            # Get education
            education = []
            try:
                education = [
                    {
                        'school': edu.school,
                        'degree': edu.degree,
                        'field': edu.field,
                        'year': edu.year
                    }
                    for edu in user.education.all()[:2]
                ]
            except Exception as e:
                logger.warning(f"Error getting education for user {user.id}: {str(e)}")
            
            return {
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'bio': getattr(user, 'bio', ''),
                'location': getattr(user, 'location', ''),
                'personality_tags': personality_tags,
                'interests': interests,
                'skills': skills,
                'work_experience': work_experience,
                'education': education,
                'recent_posts': recent_posts
            }
            
        except Exception as e:
            logger.error(f"Error building enhanced data for user {user.id}: {str(e)}")
            # Fallback to basic data
            return {
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name
            }
    
    @staticmethod
    def _generate_ai_suggestions(
        context: Dict[str, Any],
        suggestion_types: List[str] = None,
        max_suggestions: int = 3,
        custom_prompt: str = None
    ) -> List[Dict[str, Any]]:
        """Generate suggestions using Mistral AI API."""
        
        if suggestion_types is None:
            suggestion_types = ['FOLLOW_UP_QUESTIONS', 'CONVERSATION_STARTERS', 'RESPONSES', 'INTEREST_BASED', 'WORK_EDUCATION', 'PERSONALITY_MATCHED', 'CULTURAL_CONTEXT']
        
        # Build the prompt for AI
        prompt = RealTimeSuggestionService._build_ai_prompt(context, suggestion_types, max_suggestions, custom_prompt)
        
        # Prepare messages for AI
        messages = [
            {
                "role": "system",
                "content": "You are a multilingual AI assistant that helps users generate appropriate message suggestions for chat conversations in ANY language. You are fluent in all languages including but not limited to: English, Spanish, French, German, Italian, Portuguese, Russian, Chinese (Simplified and Traditional), Japanese, Korean, Arabic, Hindi, Bengali, Turkish, Dutch, Swedish, Norwegian, Danish, Finnish, Polish, Czech, Hungarian, Romanian, Bulgarian, Greek, Hebrew, Thai, Vietnamese, Indonesian, Malay, Filipino, Swahili, Kirundi, Kinyarwanda, Luganda, Yoruba, Igbo, Hausa, Amharic, Somali, Zulu, Xhosa, Afrikaans, Malagasy, Chichewa, Shona, Tswana, Sotho, and all other world languages. You analyze conversation context, user profiles, interests, posts, and other user data to provide helpful message suggestions that the USER can send to their conversation partner. IMPORTANT: You are NOT responding to the user's messages - you are generating suggestions for the user to send to others. Focus on creating follow-up questions, conversation starters, and engaging responses that the user can choose to send."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        # Debug Mistral API availability
        logger.info(f"Mistral API availability check - MISTRAL_AVAILABLE: {MISTRAL_AVAILABLE}, mistral_client: {mistral_client is not None}")
        
        try:
            # Use Mistral API
            if MISTRAL_AVAILABLE and mistral_client:
                logger.info("Attempting to call Mistral AI API...")
                
                # Make the API call using Mistral format
                response = mistral_client.chat.complete(
                    model=mistral_model,
                    messages=messages,
                    temperature=0.7,
                    top_p=1.0,
                    max_tokens=1500
                )
                
                # Extract content from Mistral response
                if response.choices:
                    ai_response = response.choices[0].message.content
                    
                    # Debug logging for AI response
                    logger.info("AI Response received:")
                    logger.info(ai_response)
                    
                    suggestions = RealTimeSuggestionService._parse_ai_response(ai_response, suggestion_types)
                    
                    # Debug logging for parsed suggestions
                    logger.info(f"Parsed {len(suggestions)} suggestions:")
                    for i, suggestion in enumerate(suggestions):
                        logger.info(f"Suggestion {i+1}: {suggestion['type']} - {suggestion['content']}")
                    
                    logger.info("Successfully generated suggestions using Mistral AI API")
                    return suggestions[:max_suggestions]
                else:
                    logger.error("Unexpected response format from Mistral AI API")
                    return []
            else:
                logger.error(f"Mistral API client not available for generating suggestions. MISTRAL_AVAILABLE: {MISTRAL_AVAILABLE}, mistral_client: {mistral_client is not None}")
                return []
                
        except Exception as e:
            logger.error(f"Error calling Mistral AI API: {str(e)}", exc_info=True)
            # Return empty list if Mistral API fails
            return []
    
    @staticmethod
    def _build_ai_prompt(context: Dict[str, Any], suggestion_types: List[str], max_suggestions: int, custom_prompt: str = None) -> str:
        """Build the prompt for AI suggestion generation with comprehensive user knowledge."""
        
        # Convert context to readable format
        participants_text = ", ".join([p['username'] for p in context['participants'] if not p['is_current_user']])
        
        # Build a more detailed conversation history
        recent_messages_text = ""
        if context['recent_messages']:
            recent_messages_text = f"Recent conversation (You = {context['current_user']['username']}):\n"
            for msg in context['recent_messages'][:15]:  # Last 15 messages for better context
                sender_name = "You" if msg['sender']['is_current_user'] else msg['sender']['username']
                timestamp = msg['created_at'][:19]  # Format timestamp
                recent_messages_text += f"[{timestamp}] {sender_name}: {msg['content']}\n"
        else:
            recent_messages_text = "This is a new conversation with no messages yet.\n"
        
        # Debug logging for conversation history
        logger.info("Conversation history being sent to AI:")
        logger.info(recent_messages_text)
        
        # Build comprehensive user profiles
        current_user_profile = RealTimeSuggestionService._format_user_profile(context['current_user'], "Current User")
        other_user_profile = ""
        if context['other_participants']:
            other_user_profile = RealTimeSuggestionService._format_user_profile(context['other_participants'], "Other Participant")
        
        # Analyze conversation patterns
        conversation_analysis = RealTimeSuggestionService._analyze_conversation_patterns(context['recent_messages'])
        
        # Analyze conversation language
        language_analysis = RealTimeSuggestionService._analyze_conversation_language(context['recent_messages'])
        
        # Debug logging for conversation analysis
        logger.info("Conversation analysis being sent to AI:")
        logger.info(conversation_analysis)
        
        # Add custom prompt if provided
        custom_instruction = ""
        if custom_prompt:
            custom_instruction = f"""
USER REQUEST:
The user specifically asked: "{custom_prompt}"

Please focus your suggestions on addressing this specific request while maintaining contextual relevance to the conversation.
"""
        
        # Add specific guidance for generating user suggestions
        user_suggestion_guidance = """
USER SUGGESTION FOCUS:
- Analyze what the conversation partner just said and generate follow-up questions
- Create engaging responses that the user can send to continue the conversation
- Suggest conversation starters based on shared interests or recent topics
- Focus on helping the user engage with their partner, not responding to the user
- Generate questions the user can ask to learn more about their partner
- Suggest ways the user can share their own experiences or opinions
"""
        
        prompt = f"""
You are a multilingual AI assistant that generates contextual message suggestions for chat conversations in ANY language. You are fluent in all world languages and can detect the language being used in conversations. Analyze the conversation carefully and provide relevant, natural suggestions based on user profiles, interests, posts, and conversation context in the appropriate language.

CRITICAL ROLE CLARIFICATION:
- You are generating SUGGESTIONS for the USER to send to their conversation partner
- You are NOT responding to the user's messages
- You are creating follow-up questions, conversation starters, and engaging responses that the user can choose to send
- Focus on what the user should say next to continue the conversation
- Generate suggestions that help the user engage with their conversation partner

CRITICAL LANGUAGE PRIORITY RULE:
- When users mix languages frequently, ALWAYS use the language of the MOST RECENT MESSAGE
- This is the most important rule - users expect responses in the language they just used
- Even if the conversation has been primarily in one language, if the last message is in a different language, use that language
- This applies to all languages including African languages (Kirundi, Kinyarwanda, Swahili, etc.)

LANGUAGE DETECTION AND RESPONSE:
- Automatically detect the primary language being used in the conversation
- Generate suggestions in the SAME language as the conversation
- If the conversation is in multiple languages, use the most recent or dominant language
- If users frequently mix languages, ALWAYS prioritize the language of the LAST MESSAGE for generating suggestions
- If it's a new conversation, detect the language from user profiles, names, or location data
- If no language context is available, default to English but be ready to switch based on conversation flow
- Understand cultural nuances and adapt suggestions to be culturally appropriate
- Pay special attention to African languages (Kirundi, Kinyarwanda, Swahili, Yoruba, Igbo, Hausa, Zulu, Xhosa, etc.) and their unique cultural contexts
- Consider regional variations within African languages and their specific cultural expressions

CONVERSATION CONTEXT:
- Type: {context['conversation_type']}
- Name: {context['conversation_name']}
- Participants: {participants_text}
- Current User: {context['current_user']['username']}

{recent_messages_text}

USER PROFILES:
{current_user_profile}

{other_user_profile}

CONVERSATION ANALYSIS:
{conversation_analysis}

LANGUAGE ANALYSIS:
{language_analysis}

{custom_instruction}

{user_suggestion_guidance}

CRITICAL USER IDENTIFICATION RULES:
- The 'current_user' is the person who will be sending the suggested messages
- You are generating suggestions for the 'current_user' to send to their conversation partner
- Focus on what the current user should say next to engage with their partner
- Do NOT respond to the current user's messages - generate suggestions for them to send
- Analyze the conversation partner's messages to create appropriate follow-up questions and responses

MULTILINGUAL CAPABILITIES:
- Detect the language of the conversation from message content, user names, locations, or profiles
- Generate suggestions in the detected language
- If conversation switches languages, adapt your suggestions accordingly
- PRIORITY RULE: When users mix languages, ALWAYS use the language of the MOST RECENT MESSAGE
- Consider cultural context and regional communication styles
- Use appropriate formality levels based on the language and culture
- Include language-specific greetings, expressions, and cultural references when relevant
- For African languages, consider traditional greetings, respect for elders, and community-oriented expressions
- Understand the importance of family and community references in African language contexts
- Adapt to formal vs informal speech patterns specific to each African language
- Include appropriate honorifics and respect terms used in African cultures

TASK:
Generate {max_suggestions} message suggestions that the CURRENT USER should send next in the appropriate language:
1. Contextually relevant to the recent messages
2. Natural and conversational in tone for the detected language
3. Appropriate for the conversation type and participants
4. Helpful for continuing the conversation
5. Leverage shared interests, recent posts, work experience, education, or personality traits when relevant
6. Include conversation starters for new conversations based on user profiles
7. Culturally appropriate for the language and region

Suggestion Types to Generate:
{', '.join(suggestion_types)}

- FOLLOW_UP_QUESTIONS: Generate questions the user can ask to continue the conversation based on what their partner just said
- CONVERSATION_STARTERS: Create engaging opening messages or topics the user can introduce
- RESPONSES: Suggest natural responses the user can send to their partner's messages
- INTEREST_BASED: Generate suggestions based on shared interests, hobbies, or activities
- WORK_EDUCATION: Create questions about work, career, or educational background
- PERSONALITY_MATCHED: Suggest messages that align with personality traits and communication style
- CULTURAL_CONTEXT: Generate culturally appropriate suggestions based on the detected language and region

Format your response as JSON:
{{
    "suggestions": [
        {{
            "type": "suggestion_type",
            "content": "message content in the appropriate language",
            "confidence": 0.85,
            "language": "detected_language_code",
            "reasoning": "brief explanation of why this suggestion fits the context, including any user profile elements used and language considerations"
        }}
    ]
}}

IMPORTANT:
- Base suggestions on actual conversation content, not generic responses
- Consider the tone and style of recent messages
- If it's a new conversation, suggest conversation starters based on shared interests, recent posts, work experience, education, or personality traits
- Make suggestions feel natural and contextual for the detected language
- If a custom request was provided, prioritize suggestions that address that specific request
- Use user profile information (interests, posts, work experience, education, personality tags) to create personalized and engaging suggestions
- For conversation starters, reference specific elements from user profiles like recent posts, shared interests, or professional background
- REMEMBER: Always suggest messages for the CURRENT USER to send, never for other participants
- ADAPT TO LANGUAGE: Ensure all suggestions are in the same language as the conversation
- CULTURAL SENSITIVITY: Consider cultural norms and communication styles for the detected language
- AFRICAN LANGUAGES: Pay special attention to traditional greetings, respect for elders, and community-oriented expressions in African languages
- REGIONAL VARIATIONS: Consider regional differences within African languages and their specific cultural expressions
"""
        
        return prompt
    
    @staticmethod
    def _format_user_profile(user_data: Dict[str, Any], user_label: str) -> str:
        """Format user profile data for AI prompt."""
        if not user_data:
            return ""
        
        profile_text = f"\n{user_label} Profile:\n"
        profile_text += f"- Name: {user_data.get('first_name', '')} {user_data.get('last_name', '')}\n"
        profile_text += f"- Username: {user_data.get('username', '')}\n"
        
        if user_data.get('bio'):
            profile_text += f"- Bio: {user_data['bio']}\n"
        
        if user_data.get('location'):
            profile_text += f"- Location: {user_data['location']}\n"
        
        # Personality tags
        if user_data.get('personality_tags'):
            tags = [tag['name'] for tag in user_data['personality_tags']]
            profile_text += f"- Personality: {', '.join(tags)}\n"
        
        # Interests
        if user_data.get('interests'):
            interests = [interest['name'] for interest in user_data['interests']]
            profile_text += f"- Interests: {', '.join(interests)}\n"
        
        # Skills
        if user_data.get('skills'):
            skills = [f"{skill['name']} (Level {skill['level']})" for skill in user_data['skills']]
            profile_text += f"- Skills: {', '.join(skills)}\n"
        
        # Work experience
        if user_data.get('work_experience'):
            profile_text += "- Recent Work Experience:\n"
            for exp in user_data['work_experience'][:2]:
                profile_text += f"  * {exp['role']} at {exp['company']} ({exp['duration']})\n"
        
        # Education
        if user_data.get('education'):
            profile_text += "- Education:\n"
            for edu in user_data['education'][:2]:
                profile_text += f"  * {edu['degree']} in {edu['field']} from {edu['school']} ({edu['year']})\n"
        
        # Recent posts
        if user_data.get('recent_posts'):
            profile_text += "- Recent Posts:\n"
            for post in user_data['recent_posts'][:2]:
                profile_text += f"  * \"{post['title']}\" - {post['content'][:100]}... (Rating: {post['rating']}, {post['comment_count']} comments)\n"
        
        return profile_text
    
    @staticmethod
    def _analyze_conversation_patterns(messages: List[Dict[str, Any]]) -> str:
        """Analyze conversation patterns to provide better context for AI."""
        if not messages:
            return "- This is a new conversation with no messages yet"
        
        analysis = []
        
        # Count messages by sender
        message_counts = {}
        for msg in messages:
            sender = msg['sender']['username']
            message_counts[sender] = message_counts.get(sender, 0) + 1
        
        # Analyze conversation flow
        if len(messages) >= 2:
            last_message = messages[0]  # Most recent
            second_last = messages[1]
            
            analysis.append(f"- Last message: {last_message['sender']['username']}: '{last_message['content'][:100]}...'")
            analysis.append(f"- Previous message: {second_last['sender']['username']}: '{second_last['content'][:100]}...'")
            
            # Determine who should respond next
            if last_message['sender']['username'] != second_last['sender']['username']:
                analysis.append(f"- CONVERSATION FLOW: {last_message['sender']['username']} just sent a message")
                analysis.append(f"- USER ACTION NEEDED: Generate suggestions for what the user should say in response")
            else:
                analysis.append(f"- CONVERSATION FLOW: {last_message['sender']['username']} sent consecutive messages")
                analysis.append(f"- USER ACTION NEEDED: Generate follow-up questions or conversation starters for the user to send")
        
        # Analyze conversation length
        if len(messages) < 5:
            analysis.append("- Short conversation - focus on conversation starters and engagement")
        elif len(messages) < 20:
            analysis.append("- Medium conversation - build on existing topics")
        else:
            analysis.append("- Long conversation - focus on deepening engagement or topic transitions")
        
        # Add language analysis
        language_analysis = RealTimeSuggestionService._analyze_conversation_language(messages)
        analysis.extend(language_analysis)
        
        return "\n".join(analysis)
    
    @staticmethod
    def _analyze_conversation_language(messages: List[Dict[str, Any]]) -> List[str]:
        """Analyze the language patterns in the conversation."""
        analysis = []
        
        if not messages:
            analysis.append("- LANGUAGE: No messages to analyze")
            return analysis
        
        # PRIORITY: Analyze the most recent message first for language detection
        if messages:
            last_message = messages[0]  # Most recent message
            last_message_content = last_message['content']
            analysis.append(f"- LAST MESSAGE LANGUAGE: Analyzing '{last_message_content[:50]}...' for primary language")
            analysis.append("- PRIORITY: Using language of the most recent message for suggestions")
        
        # Simple language detection based on character sets and common patterns
        # This is a basic implementation - the AI will do more sophisticated detection
        
        # Check for non-Latin characters
        non_latin_chars = 0
        total_chars = 0
        
        for msg in messages[:10]:  # Check first 10 messages
            content = msg['content']
            total_chars += len(content)
            
            # Count non-Latin characters (basic detection)
            for char in content:
                if ord(char) > 127:  # Non-ASCII characters
                    non_latin_chars += 1
        
        if total_chars > 0:
            non_latin_ratio = non_latin_chars / total_chars
            
            if non_latin_ratio > 0.3:
                analysis.append("- LANGUAGE: High probability of non-Latin script (Chinese, Japanese, Korean, Arabic, etc.)")
                analysis.append("- SUGGESTION: Generate suggestions in the detected script/language")
            elif non_latin_ratio > 0.1:
                analysis.append("- LANGUAGE: Mixed script detected (may include accented characters, Cyrillic, etc.)")
                analysis.append("- SUGGESTION: Adapt suggestions to include appropriate characters and cultural context")
            else:
                analysis.append("- LANGUAGE: Primarily Latin script detected")
                analysis.append("- SUGGESTION: Generate suggestions in appropriate Latin-based language")
        
        # Check for specific language indicators - PRIORITIZE LAST MESSAGE
        if messages:
            last_message_content = messages[0]['content']  # Most recent message
            analysis.append(f"- ANALYZING LAST MESSAGE: '{last_message_content[:100]}...' for language indicators")
        
        all_content = " ".join([msg['content'] for msg in messages[:5]])
        
        # Common language indicators (basic patterns)
        language_indicators = {
            'spanish': ['hola', 'gracias', 'por favor', 'que', 'como', 'donde'],
            'french': ['bonjour', 'merci', 's\'il vous plaît', 'comment', 'où', 'quand'],
            'german': ['hallo', 'danke', 'bitte', 'wie', 'wo', 'wann'],
            'italian': ['ciao', 'grazie', 'per favore', 'come', 'dove', 'quando'],
            'portuguese': ['olá', 'obrigado', 'por favor', 'como', 'onde', 'quando'],
            'russian': ['привет', 'спасибо', 'пожалуйста', 'как', 'где', 'когда'],
            'chinese': ['你好', '谢谢', '请', '怎么', '哪里', '什么时候'],
            'japanese': ['こんにちは', 'ありがとう', 'お願い', 'どう', 'どこ', 'いつ'],
            'korean': ['안녕하세요', '감사합니다', '부탁합니다', '어떻게', '어디', '언제'],
            'arabic': ['مرحبا', 'شكرا', 'من فضلك', 'كيف', 'أين', 'متى'],
            'hindi': ['नमस्ते', 'धन्यवाद', 'कृपया', 'कैसे', 'कहाँ', 'कब'],
            'kirundi': ['amahoro', 'urakoze', 'ndakusaba', 'iki', 'hehe', 'ryari'],
            'kinyarwanda': ['murakoze', 'ndakusaba', 'iki', 'hehe', 'ryari', 'uburyo'],
            'luganda': ['ki kati', 'webale', 'ndakusaba', 'ki', 'wa', 'ddi'],
            'yoruba': ['bawo', 'o se', 'jowo', 'kini', 'ibo', 'nigba wo'],
            'igbo': ['kedu', 'daalu', 'biko', 'gini', 'ebe', 'mgbe ole'],
            'hausa': ['sannu', 'na gode', 'don Allah', 'me', 'ina', 'yaushe'],
            'amharic': ['selam', 'ameseginalehu', 'ebakih', 'min', 'yet', 'met'],
            'somali': ['salaam', 'mahadsanid', 'fadlan', 'maxay', 'xagee', 'goorta'],
            'zulu': ['sawubona', 'ngiyabonga', 'ngicela', 'yini', 'kuphi', 'nini'],
            'xhosa': ['molo', 'enkosi', 'ndicela', 'yintoni', 'phi', 'xa'],
            'afrikaans': ['hallo', 'dankie', 'asseblief', 'wat', 'waar', 'wanneer'],
            'malagasy': ['salama', 'misaotra', 'azafady', 'inona', 'aiza', 'oviana'],
            'chichewa': ['moni', 'zikomo', 'chonde', 'chiyani', 'kuti', 'liti'],
            'shona': ['mhoro', 'tenda', 'ndapota', 'chii', 'kupi', 'rinhi'],
            'tswana': ['dumela', 'ke a leboga', 'tswee tswee', 'eng', 'kae', 'neng'],
            'sotho': ['lumela', 'ke a leboha', 'ka kopo', 'eng', 'kae', 'neng'],
            'swahili': ['jambo', 'asante', 'tafadhali', 'nini', 'wapi', 'lini']
        }
        
        # PRIORITY: Check last message first for language indicators
        last_message_languages = []
        if messages:
            last_content = messages[0]['content'].lower()
            for lang, indicators in language_indicators.items():
                for indicator in indicators:
                    if indicator.lower() in last_content:
                        last_message_languages.append(lang)
                        break
        
        if last_message_languages:
            analysis.append(f"- LAST MESSAGE LANGUAGE DETECTED: {', '.join(last_message_languages)}")
            analysis.append("- PRIORITY: Using last message language for suggestions")
        
        # Check overall conversation for language patterns
        detected_languages = []
        for lang, indicators in language_indicators.items():
            for indicator in indicators:
                if indicator.lower() in all_content.lower():
                    detected_languages.append(lang)
                    break
        
        if detected_languages:
            analysis.append(f"- OVERALL CONVERSATION LANGUAGES: {', '.join(detected_languages)}")
            if last_message_languages:
                analysis.append("- CONFLICT RESOLUTION: Last message language takes priority over overall conversation language")
            else:
                analysis.append("- SUGGESTION: Generate suggestions in the detected language(s)")
        else:
            analysis.append("- LANGUAGE: No specific language indicators detected")
            analysis.append("- SUGGESTION: Use English as default, but be ready to adapt based on conversation flow")
        
        # Add specific instruction for mixed language scenarios
        if len(detected_languages) > 1:
            analysis.append("- MIXED LANGUAGE DETECTED: Multiple languages found in conversation")
            analysis.append("- CRITICAL RULE: Always use the language of the MOST RECENT MESSAGE for suggestions")
            analysis.append("- REASONING: User is likely code-switching and expects response in the language they just used")
        
        return analysis
    
    @staticmethod
    def _parse_ai_response(ai_response: str, suggestion_types: List[str]) -> List[Dict[str, Any]]:
        """Parse the AI response into structured suggestions."""
        try:
            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                response_data = json.loads(json_match.group())
                suggestions = response_data.get('suggestions', [])
                
                # Validate and clean suggestions
                cleaned_suggestions = []
                for suggestion in suggestions:
                    if all(key in suggestion for key in ['type', 'content', 'confidence']):
                        # Ensure suggestion type is valid
                        if suggestion['type'] not in suggestion_types:
                            suggestion['type'] = suggestion_types[0]
                        
                        # Ensure confidence is between 0 and 1
                        confidence = max(0.0, min(1.0, float(suggestion['confidence'])))
                        
                        # Handle language field (new addition)
                        detected_language = suggestion.get('language', 'en')  # Default to English
                        
                        cleaned_suggestions.append({
                            'type': suggestion['type'],
                            'content': suggestion['content'],
                            'confidence': confidence,
                            'language': detected_language,
                            'context': {
                                'reasoning': suggestion.get('reasoning', ''),
                                'ai_generated': True,
                                'language_detected': detected_language
                            }
                        })
                
                return cleaned_suggestions
                
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Error parsing AI response: {str(e)}")
        
        # Return empty list if parsing fails
        return [] 