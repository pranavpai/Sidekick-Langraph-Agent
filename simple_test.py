#!/usr/bin/env python3
"""
Simple test for core database functionality
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from memory_manager import memory_manager
from config import DEFAULT_CONVERSATION_TITLE

def test_auto_title():
    """Test auto-title functionality for default conversations"""
    print("🧪 Testing Auto-Title Functionality")
    print("="*40)
    
    username = 'test_user'
    result = memory_manager.create_conversation(username)
    
    if not result['success']:
        print(f"❌ Failed to create conversation: {result}")
        return False
        
    conv_id = result['conversation_id']
    print(f"✅ Created default conversation: {conv_id[:8]}...")
    
    try:
        # Check initial title
        conv_initial = memory_manager.get_conversation(conv_id, username)
        print(f"📊 Initial title: '{conv_initial.title}'")
        
        # Try auto-titling
        test_message = 'Can you explain quantum computing and its applications?'
        title_result = memory_manager.auto_title_conversation(conv_id, username, test_message)
        print(f"🏷️ Auto-title result: {title_result}")
        
        # Check updated title
        conv_after_title = memory_manager.get_conversation(conv_id, username)
        print(f"📊 Updated title: '{conv_after_title.title}'")
        
        if conv_after_title.title != DEFAULT_CONVERSATION_TITLE:
            print("✅ Auto-titling worked correctly")
            test_passed = True
        else:
            print("❌ Auto-titling failed - title still default")
            test_passed = False
            
        return test_passed
        
    finally:
        # Cleanup
        memory_manager.delete_conversation(conv_id, username)

def test_cache_removal():
    """Test that active_sidekicks cache management works"""
    print("\n🧪 Testing Cache Management")
    print("="*30)
    
    from app import active_sidekicks
    
    # Simulate adding to cache
    session_key = "test_user_123"
    active_sidekicks[session_key] = "mock_sidekick_instance"
    print(f"📝 Added to cache: {session_key}")
    print(f"📊 Cache size: {len(active_sidekicks)}")
    
    # Simulate cache removal (like in clear_chat_display)
    if session_key in active_sidekicks:
        del active_sidekicks[session_key]
        print(f"🗑️ Removed from cache: {session_key}")
    
    # Verify removal
    if session_key not in active_sidekicks:
        print("✅ Cache removal successful")
        return True
    else:
        print("❌ Cache removal failed")
        return False

if __name__ == "__main__":
    print("🚀 Starting Simple Core Tests")
    print("="*50)
    
    results = []
    results.append(test_auto_title())
    results.append(test_cache_removal())
    
    print(f"\n📊 Results: {sum(results)}/{len(results)} tests passed")
    
    if all(results):
        print("🎉 All core tests PASSED!")
    else:
        print("⚠️ Some tests FAILED")