# Generated by Django 5.0.1 on 2025-06-16 15:58

import django.contrib.postgres.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assistant', '0002_remove_chatmessage_assistant_c_user_id_634679_idx_and_more'),
        ('community', '0002_initial'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('users', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AIRatingInsight',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_id', models.PositiveIntegerField()),
                ('sentiment_score', models.FloatField(default=0.0)),
                ('rating_patterns', models.JSONField(default=dict)),
                ('quality_indicators', models.JSONField(default=dict)),
                ('engagement_prediction', models.FloatField(default=0.0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='AssistantInterest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vector', django.contrib.postgres.fields.ArrayField(base_field=models.FloatField(), size=1536)),
                ('weight', models.FloatField(default=1.0)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('evolution_history', models.JSONField(default=list)),
                ('related_interests', models.JSONField(default=list)),
            ],
        ),
        migrations.CreateModel(
            name='AssistantMemory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('personality_profile', models.JSONField(default=dict)),
                ('learning_data', models.JSONField(default=dict)),
                ('last_interaction', models.DateTimeField(auto_now=True)),
                ('context_window', models.JSONField(default=list)),
                ('community_engagement', models.JSONField(default=dict)),
                ('content_preferences', models.JSONField(default=dict)),
                ('interaction_patterns', models.JSONField(default=dict)),
                ('notification_preferences', models.JSONField(default=dict)),
                ('notification_frequency', models.CharField(choices=[('realtime', 'Real-time'), ('daily', 'Daily Digest'), ('weekly', 'Weekly Summary'), ('custom', 'Custom')], default='realtime', max_length=20)),
                ('notification_quiet_hours', models.JSONField(default=dict, help_text='Store quiet hours preferences in 24-hour format')),
                ('notification_priority_threshold', models.IntegerField(default=0, help_text='Minimum priority level for notifications')),
                ('suggestion_preferences', models.JSONField(default=dict)),
                ('suggestion_history', models.JSONField(default=dict)),
                ('learning_preferences', models.JSONField(default=dict)),
                ('interest_alchemy_preferences', models.JSONField(default=dict)),
                ('curiosity_profile', models.JSONField(default=dict)),
                ('discovery_history', models.JSONField(default=dict)),
                ('rating_insights', models.JSONField(default=dict)),
                ('rating_preferences', models.JSONField(default=dict)),
            ],
        ),
        migrations.CreateModel(
            name='AssistantNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notification_type', models.CharField(choices=[('interest_match', 'Interest Match'), ('community_suggestion', 'Community Suggestion'), ('content_recommendation', 'Content Recommendation'), ('learning_insight', 'Learning Insight'), ('activity_summary', 'Activity Summary'), ('connection_suggestion', 'Connection Suggestion'), ('skill_development', 'Skill Development'), ('achievement_progress', 'Achievement Progress')], max_length=50)),
                ('title', models.CharField(max_length=255)),
                ('message', models.TextField()),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('priority', models.IntegerField(default=0)),
                ('action_required', models.BooleanField(default=False)),
                ('action_taken', models.BooleanField(default=False)),
                ('object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('context', models.JSONField(blank=True, default=dict)),
                ('confidence_score', models.FloatField(default=0.0)),
                ('feedback', models.JSONField(blank=True, default=dict)),
            ],
            options={
                'ordering': ['-priority', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='CommunityScore',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_ratings', models.IntegerField(default=0)),
                ('average_score', models.FloatField(default=0.0)),
                ('rating_distribution', models.JSONField(default=dict)),
                ('engagement_score', models.FloatField(default=0.0)),
                ('quality_score', models.FloatField(default=0.0)),
                ('trending_score', models.FloatField(default=0.0)),
                ('last_updated', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='CommunitySuggestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('suggestion_type', models.CharField(choices=[('post', 'Post'), ('community', 'Community'), ('connection', 'Connection'), ('content', 'Content'), ('skill', 'Skill'), ('interest', 'Interest')], max_length=20)),
                ('score', models.FloatField(default=0.0)),
                ('confidence', models.FloatField(default=0.0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_rejected', models.BooleanField(default=False)),
                ('rejected_at', models.DateTimeField(blank=True, null=True)),
                ('object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('reasoning', models.JSONField(default=dict)),
                ('features', models.JSONField(default=dict)),
                ('user_feedback', models.JSONField(default=dict)),
                ('member_similarity', models.FloatField(default=0.0)),
                ('activity_match', models.FloatField(default=0.0)),
                ('growth_potential', models.FloatField(default=0.0)),
                ('topic_relevance', models.FloatField(default=0.0)),
            ],
            options={
                'ordering': ['-score', '-confidence'],
            },
        ),
        migrations.CreateModel(
            name='ConnectionSuggestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('suggestion_type', models.CharField(choices=[('post', 'Post'), ('community', 'Community'), ('connection', 'Connection'), ('content', 'Content'), ('skill', 'Skill'), ('interest', 'Interest')], max_length=20)),
                ('score', models.FloatField(default=0.0)),
                ('confidence', models.FloatField(default=0.0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_rejected', models.BooleanField(default=False)),
                ('rejected_at', models.DateTimeField(blank=True, null=True)),
                ('object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('reasoning', models.JSONField(default=dict)),
                ('features', models.JSONField(default=dict)),
                ('user_feedback', models.JSONField(default=dict)),
                ('mutual_connections', models.IntegerField(default=0)),
                ('interest_overlap', models.FloatField(default=0.0)),
                ('activity_compatibility', models.FloatField(default=0.0)),
                ('communication_style_match', models.FloatField(default=0.0)),
                ('potential_collaboration_score', models.FloatField(default=0.0)),
                ('complementary_interests', models.JSONField(default=dict, help_text='Store Interest Alchemy pairs that connect the users')),
                ('curiosity_collisions', models.JSONField(default=list, help_text='Store relevant Curiosity Collisions between users')),
                ('micro_community_overlap', models.JSONField(default=dict, help_text='Track shared micro-community memberships')),
                ('interest_alchemy_score', models.FloatField(default=0.0, help_text='Score based on Interest Alchemy compatibility')),
            ],
            options={
                'ordering': ['-score', '-confidence'],
            },
        ),
        migrations.CreateModel(
            name='ContentRecommendation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('suggestion_type', models.CharField(choices=[('post', 'Post'), ('community', 'Community'), ('connection', 'Connection'), ('content', 'Content'), ('skill', 'Skill'), ('interest', 'Interest')], max_length=20)),
                ('score', models.FloatField(default=0.0)),
                ('confidence', models.FloatField(default=0.0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_rejected', models.BooleanField(default=False)),
                ('rejected_at', models.DateTimeField(blank=True, null=True)),
                ('object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('reasoning', models.JSONField(default=dict)),
                ('features', models.JSONField(default=dict)),
                ('user_feedback', models.JSONField(default=dict)),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField()),
                ('url', models.URLField()),
                ('source', models.CharField(max_length=100)),
                ('engagement_metrics', models.JSONField(default=dict)),
                ('content_vector', django.contrib.postgres.fields.ArrayField(base_field=models.FloatField(), size=1536)),
            ],
            options={
                'ordering': ['-score', '-confidence'],
            },
        ),
        migrations.CreateModel(
            name='CuriosityCollision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('discovered_at', models.DateTimeField(auto_now_add=True)),
                ('impact_score', models.FloatField(default=0.0)),
                ('insights', models.JSONField(default=list)),
                ('follow_up_actions', models.JSONField(default=list)),
            ],
        ),
        migrations.CreateModel(
            name='InterestAlchemy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('complementarity_score', models.FloatField(default=0.0)),
                ('discovery_potential', models.FloatField(default=0.0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('success_metrics', models.JSONField(default=dict)),
                ('micro_communities', models.JSONField(default=list)),
            ],
        ),
        migrations.CreateModel(
            name='MicroCommunity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('members_count', models.IntegerField(default=0)),
                ('activity_score', models.FloatField(default=0.0)),
                ('discovery_insights', models.JSONField(default=list)),
            ],
            options={
                'verbose_name_plural': 'Micro Communities',
            },
        ),
        migrations.CreateModel(
            name='PostSuggestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('suggestion_type', models.CharField(choices=[('post', 'Post'), ('community', 'Community'), ('connection', 'Connection'), ('content', 'Content'), ('skill', 'Skill'), ('interest', 'Interest')], max_length=20)),
                ('score', models.FloatField(default=0.0)),
                ('confidence', models.FloatField(default=0.0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_rejected', models.BooleanField(default=False)),
                ('rejected_at', models.DateTimeField(blank=True, null=True)),
                ('object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('reasoning', models.JSONField(default=dict)),
                ('features', models.JSONField(default=dict)),
                ('user_feedback', models.JSONField(default=dict)),
                ('relevance_factors', models.JSONField(default=dict)),
                ('engagement_prediction', models.FloatField(default=0.0)),
                ('content_similarity', models.FloatField(default=0.0)),
                ('user_history_impact', models.FloatField(default=0.0)),
            ],
            options={
                'ordering': ['-score', '-confidence'],
            },
        ),
        migrations.CreateModel(
            name='RatingPattern',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pattern_type', models.CharField(max_length=50)),
                ('confidence', models.FloatField(default=0.0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('pattern_data', models.JSONField(default=dict)),
            ],
        ),
        migrations.CreateModel(
            name='SkillRecommendation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('suggestion_type', models.CharField(choices=[('post', 'Post'), ('community', 'Community'), ('connection', 'Connection'), ('content', 'Content'), ('skill', 'Skill'), ('interest', 'Interest')], max_length=20)),
                ('score', models.FloatField(default=0.0)),
                ('confidence', models.FloatField(default=0.0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_rejected', models.BooleanField(default=False)),
                ('rejected_at', models.DateTimeField(blank=True, null=True)),
                ('object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('reasoning', models.JSONField(default=dict)),
                ('features', models.JSONField(default=dict)),
                ('user_feedback', models.JSONField(default=dict)),
                ('skill_name', models.CharField(max_length=100)),
                ('current_level', models.FloatField(default=0.0)),
                ('target_level', models.FloatField(default=0.0)),
                ('learning_path', models.JSONField(default=list)),
                ('resources', models.JSONField(default=list)),
                ('estimated_time', models.IntegerField(default=0)),
                ('priority', models.IntegerField(default=0)),
            ],
            options={
                'ordering': ['-priority', '-score'],
            },
        ),
        migrations.CreateModel(
            name='UserInterest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('interest', models.CharField(max_length=100)),
                ('vector', django.contrib.postgres.fields.ArrayField(base_field=models.FloatField(), size=1536)),
                ('weight', models.FloatField(default=1.0)),
                ('last_updated', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AlterModelOptions(
            name='chatmessage',
            options={'ordering': ['timestamp']},
        ),
        migrations.RenameField(
            model_name='chatmessage',
            old_name='created_at',
            new_name='timestamp',
        ),
        migrations.RemoveField(
            model_name='chatmessage',
            name='response',
        ),
        migrations.AddField(
            model_name='chatmessage',
            name='comment',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assistant_chats', to='community.comment'),
        ),
        migrations.AddField(
            model_name='chatmessage',
            name='community',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assistant_chats', to='community.community'),
        ),
        migrations.AddField(
            model_name='chatmessage',
            name='community_post',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assistant_chats', to='community.communitypost'),
        ),
        migrations.AddField(
            model_name='chatmessage',
            name='context',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='chatmessage',
            name='is_user_message',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='chatmessage',
            name='personal_post',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assistant_chats', to='community.personalpost'),
        ),
        migrations.AlterField(
            model_name='chatmessage',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assistant_chats', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddIndex(
            model_name='chatmessage',
            index=models.Index(fields=['user', 'timestamp'], name='assistant_c_user_id_3ff5e9_idx'),
        ),
        migrations.AddIndex(
            model_name='chatmessage',
            index=models.Index(fields=['community', 'timestamp'], name='assistant_c_communi_aba5b3_idx'),
        ),
        migrations.AddIndex(
            model_name='chatmessage',
            index=models.Index(fields=['personal_post', 'timestamp'], name='assistant_c_persona_c8bd06_idx'),
        ),
        migrations.AddIndex(
            model_name='chatmessage',
            index=models.Index(fields=['community_post', 'timestamp'], name='assistant_c_communi_d2aa2c_idx'),
        ),
        migrations.AddField(
            model_name='airatinginsight',
            name='content_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype'),
        ),
        migrations.AddField(
            model_name='assistantinterest',
            name='user_interest',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assistant_data', to='users.userinterest'),
        ),
        migrations.AddField(
            model_name='assistantmemory',
            name='user',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='assistant_memory', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='assistantnotification',
            name='content_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype'),
        ),
        migrations.AddField(
            model_name='assistantnotification',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assistant_notifications', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='communityscore',
            name='community_post',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='community_score', to='community.communitypost'),
        ),
        migrations.AddField(
            model_name='communityscore',
            name='personal_post',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='community_score', to='community.personalpost'),
        ),
        migrations.AddField(
            model_name='communitysuggestion',
            name='community',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ai_suggestions', to='community.community'),
        ),
        migrations.AddField(
            model_name='communitysuggestion',
            name='content_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype'),
        ),
        migrations.AddField(
            model_name='communitysuggestion',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(class)s_suggestions', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='connectionsuggestion',
            name='content_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype'),
        ),
        migrations.AddField(
            model_name='connectionsuggestion',
            name='suggested_user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ai_connection_suggestions', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='connectionsuggestion',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(class)s_suggestions', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='contentrecommendation',
            name='content_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype'),
        ),
        migrations.AddField(
            model_name='contentrecommendation',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(class)s_suggestions', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='curiositycollision',
            name='interests',
            field=models.ManyToManyField(related_name='collisions', to='users.userinterest'),
        ),
        migrations.AddField(
            model_name='curiositycollision',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='curiosity_collisions', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='interestalchemy',
            name='interest1',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='alchemy_as_primary', to='users.userinterest'),
        ),
        migrations.AddField(
            model_name='interestalchemy',
            name='interest2',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='alchemy_as_secondary', to='users.userinterest'),
        ),
        migrations.AddField(
            model_name='microcommunity',
            name='interest_alchemy',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='communities', to='assistant.interestalchemy'),
        ),
        migrations.AddField(
            model_name='microcommunity',
            name='parent_community',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='micro_communities', to='community.community'),
        ),
        migrations.AddField(
            model_name='postsuggestion',
            name='community_post',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='ai_suggestions', to='community.communitypost'),
        ),
        migrations.AddField(
            model_name='postsuggestion',
            name='content_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype'),
        ),
        migrations.AddField(
            model_name='postsuggestion',
            name='personal_post',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='ai_suggestions', to='community.personalpost'),
        ),
        migrations.AddField(
            model_name='postsuggestion',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(class)s_suggestions', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='ratingpattern',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rating_patterns', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='skillrecommendation',
            name='content_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype'),
        ),
        migrations.AddField(
            model_name='skillrecommendation',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(class)s_suggestions', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='userinterest',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assistant_interests', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddIndex(
            model_name='airatinginsight',
            index=models.Index(fields=['content_type', 'object_id'], name='assistant_a_content_a97638_idx'),
        ),
        migrations.AddIndex(
            model_name='airatinginsight',
            index=models.Index(fields=['sentiment_score'], name='assistant_a_sentime_a4ffeb_idx'),
        ),
        migrations.AddIndex(
            model_name='assistantinterest',
            index=models.Index(fields=['user_interest', 'last_updated'], name='assistant_a_user_in_b593d6_idx'),
        ),
        migrations.AddIndex(
            model_name='assistantmemory',
            index=models.Index(fields=['user', 'last_interaction'], name='assistant_a_user_id_b5563e_idx'),
        ),
        migrations.AddIndex(
            model_name='assistantnotification',
            index=models.Index(fields=['user', 'is_read', 'created_at'], name='assistant_a_user_id_43b695_idx'),
        ),
        migrations.AddIndex(
            model_name='assistantnotification',
            index=models.Index(fields=['notification_type', 'priority'], name='assistant_a_notific_8f6d56_idx'),
        ),
        migrations.AddIndex(
            model_name='communityscore',
            index=models.Index(fields=['average_score', 'engagement_score'], name='assistant_c_average_40ed3c_idx'),
        ),
        migrations.AddIndex(
            model_name='communityscore',
            index=models.Index(fields=['trending_score'], name='assistant_c_trendin_bc91c0_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='communitysuggestion',
            unique_together={('user', 'community')},
        ),
        migrations.AlterUniqueTogether(
            name='connectionsuggestion',
            unique_together={('user', 'suggested_user')},
        ),
        migrations.AddIndex(
            model_name='curiositycollision',
            index=models.Index(fields=['user', 'discovered_at'], name='assistant_c_user_id_253917_idx'),
        ),
        migrations.AddIndex(
            model_name='curiositycollision',
            index=models.Index(fields=['impact_score'], name='assistant_c_impact__ac2831_idx'),
        ),
        migrations.AddIndex(
            model_name='interestalchemy',
            index=models.Index(fields=['complementarity_score'], name='assistant_i_complem_7ec739_idx'),
        ),
        migrations.AddIndex(
            model_name='interestalchemy',
            index=models.Index(fields=['discovery_potential'], name='assistant_i_discove_aee44e_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='interestalchemy',
            unique_together={('interest1', 'interest2')},
        ),
        migrations.AddIndex(
            model_name='microcommunity',
            index=models.Index(fields=['activity_score'], name='assistant_m_activit_cbbf0d_idx'),
        ),
        migrations.AddIndex(
            model_name='microcommunity',
            index=models.Index(fields=['members_count'], name='assistant_m_members_169445_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='postsuggestion',
            unique_together={('user', 'community_post'), ('user', 'personal_post')},
        ),
        migrations.AddIndex(
            model_name='ratingpattern',
            index=models.Index(fields=['user', 'pattern_type'], name='assistant_r_user_id_0ac9c3_idx'),
        ),
        migrations.AddIndex(
            model_name='userinterest',
            index=models.Index(fields=['user', 'interest'], name='assistant_u_user_id_b1d86c_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='userinterest',
            unique_together={('user', 'interest')},
        ),
    ]
