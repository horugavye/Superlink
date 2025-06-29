#!/usr/bin/env python3
"""
Django script to create a superuser with predefined credentials.
This script can be run independently of the Django management command.
"""

import os
import sys
import django
from django.contrib.auth import get_user_model
from django.core.management import execute_from_command_line

# Add the backend directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'superlink.settings')
django.setup()

def create_superuser():
    """Create a superuser with predefined credentials."""
    User = get_user_model()
    
    # Predefined credentials
    username = "horugavye"
    email = "horugavye.officiall@gmail.com"
    password = "Horugavye@2024"
    
    print("=== Django Superuser Creation ===")
    print(f"Creating superuser with the following credentials:")
    print(f"Username: {username}")
    print(f"Email: {email}")
    print(f"Password: {'*' * len(password)}")
    print()
    
    # Check if user already exists
    if User.objects.filter(username=username).exists():
        print(f"❌ Error: A user with username '{username}' already exists.")
        return False
    
    if User.objects.filter(email=email).exists():
        print(f"❌ Error: A user with email '{email}' already exists.")
        return False
    
    try:
        # Create the superuser
        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )
        
        print(f"✅ Superuser '{username}' created successfully!")
        print(f"Username: {username}")
        print(f"Email: {email}")
        print(f"Is superuser: {user.is_superuser}")
        print(f"Is staff: {user.is_staff}")
        
    except Exception as e:
        print(f"❌ Error creating superuser: {e}")
        return False
    
    return True

def main():
    """Main function to run the script."""
    try:
        success = create_superuser()
        if success:
            print("\n🎉 Superuser creation completed successfully!")
        else:
            print("\n💥 Superuser creation failed!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 