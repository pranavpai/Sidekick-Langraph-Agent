#!/usr/bin/env python3
"""
Quick test for database functionality only
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from memory_manager import memory_manager
from config import DEFAULT_CONVERSATION_TITLE

print("🧪 Quick Database Tests")
print("="*30)

# Test 1: Auto-title functionality
print("\n📝 Test 1: Auto-title")
username = 'test_user'
result = memory_manager.create_conversation(username)

if result['success']:
    conv_id = result['conversation_id']
    print(f"✅ Created conversation: {conv_id[:8]}...")
    
    # Check initial title
    conv = memory_manager.get_conversation(conv_id, username)
    print(f"Initial title: '{conv.title}'")
    
    # Auto-title
    test_message = 'What is machine learning?'
    title_result = memory_manager.auto_title_conversation(conv_id, username, test_message)
    print(f"Auto-title success: {title_result}")
    
    # Check new title
    conv_updated = memory_manager.get_conversation(conv_id, username)
    print(f"New title: '{conv_updated.title}'")
    
    if conv_updated.title != DEFAULT_CONVERSATION_TITLE:
        print("✅ Auto-title PASSED")
    else:
        print("❌ Auto-title FAILED")
    
    # Cleanup
    memory_manager.delete_conversation(conv_id, username)

# Test 2: Clear functionality
print("\n📝 Test 2: Clear conversation")
result2 = memory_manager.create_conversation(username, "Custom Title")

if result2['success']:
    conv_id2 = result2['conversation_id']
    print(f"✅ Created conversation with custom title")
    
    # Clear it
    clear_result = memory_manager.clear_conversation_history(conv_id2, username)
    print(f"Clear success: {clear_result['success']}")
    
    # Check title was reset
    conv_cleared = memory_manager.get_conversation(conv_id2, username)
    print(f"Title after clear: '{conv_cleared.title}'")
    
    if conv_cleared.title == DEFAULT_CONVERSATION_TITLE:
        print("✅ Clear title reset PASSED")
    else:
        print("❌ Clear title reset FAILED")
    
    # Cleanup
    memory_manager.delete_conversation(conv_id2, username)

print("\n🎯 Quick tests completed")