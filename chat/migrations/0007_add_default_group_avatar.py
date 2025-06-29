from django.db import migrations, models
import os
from django.conf import settings

def ensure_default_avatar_exists(apps, schema_editor):
    # Get the default avatar path
    default_avatar_path = os.path.join(settings.MEDIA_ROOT, 'avatars', 'groudefault.jpeg')
    
    # Create the avatars directory if it doesn't exist
    os.makedirs(os.path.dirname(default_avatar_path), exist_ok=True)
    
    # If the default avatar doesn't exist, create it
    if not os.path.exists(default_avatar_path):
        # Create a simple default avatar
        from PIL import Image, ImageDraw
        img = Image.new('RGB', (200, 200), color='#1f6feb')
        draw = ImageDraw.Draw(img)
        draw.ellipse([50, 50, 150, 150], fill='white')
        img.save(default_avatar_path)

class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0006_alter_group_avatar'),
    ]

    operations = [
        migrations.RunPython(ensure_default_avatar_exists),
    ] 