#!/usr/bin/env python3
"""
Test script to verify Clear Chat Display and Default Conversation Auto-Titling fixes
Tests both issues reported by the user
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from memory_manager import memory_manager
from sidekick import Sidekick
from app import active_sidekicks

async def test_clear_chat_display_no_toggle():
    """Test that Clear Chat Display completely clears state and has no toggle behavior"""
    print("\n🧪 Test 1: Clear Chat Display - No Toggle Behavior")
    print("="*55)
    
    # Create a test conversation
    username = "test_user"
    test_conv_result = memory_manager.create_conversation(username, "Test Clear No Toggle")
    
    if not test_conv_result["success"]:
        print(f"❌ Failed to create test conversation: {test_conv_result}")
        return False
        
    conversation_id = test_conv_result["conversation_id"]
    print(f"📝 Created test conversation: {conversation_id}")
    
    # Create and add Sidekick to active cache (simulating normal usage)
    sidekick = Sidekick(username=username, conversation_id=conversation_id)
    await sidekick.setup()
    session_key = f"{username}_{conversation_id}"
    active_sidekicks[session_key] = sidekick
    print(f"🎯 Added Sidekick to active cache: {session_key}")
    
    try:
        # Step 1: Send a message to create some history
        print("\n📤 Step 1: Creating conversation history")
        await sidekick.run_superstep(
            "What is machine learning?", 
            "Provide a comprehensive answer", 
            [], 
            original_message="What is machine learning?"
        )
        
        # Verify conversation has content
        history_before = await sidekick.get_conversation_history()
        conv_before = memory_manager.get_conversation(conversation_id, username)
        print(f"📊 Before clear - History: {len(history_before)} msgs, Title: '{conv_before.title}', Count: {conv_before.message_count}")
        
        # Step 2: Clear the conversation using the enhanced clear function
        print("\n🧹 Step 2: Clearing conversation history")
        clear_result = memory_manager.clear_conversation_history(conversation_id, username)
        print(f"🧹 Clear result: {clear_result}")
        
        if not clear_result["success"]:
            print("❌ Clear operation failed")
            return False
        
        # Step 3: Remove from active cache (simulating clear_chat_display)
        if session_key in active_sidekicks:
            active_sidekicks[session_key].cleanup()
            del active_sidekicks[session_key]
            print(f"🗑️ Removed from active cache: {session_key}")
        
        # Step 4: Verify conversation is reset to default state
        conv_after_clear = memory_manager.get_conversation(conversation_id, username)
        print(f"📊 After clear - Title: '{conv_after_clear.title}', Count: {conv_after_clear.message_count}")
        
        # Step 5: Create new Sidekick (simulating clicking on conversation in dropdown)
        print("\n🔄 Step 3: Simulating dropdown click (new Sidekick)")
        new_sidekick = Sidekick(username=username, conversation_id=conversation_id)
        await new_sidekick.setup()
        
        # Step 6: Check history multiple times (testing for toggle behavior)
        print("\n🔍 Step 4: Testing for toggle behavior (multiple history checks)")
        
        history_check_1 = await new_sidekick.get_conversation_history()
        print(f"📊 History check 1: {len(history_check_1)} messages")
        
        history_check_2 = await new_sidekick.get_conversation_history()
        print(f"📊 History check 2: {len(history_check_2)} messages")
        
        history_check_3 = await new_sidekick.get_conversation_history()
        print(f"📊 History check 3: {len(history_check_3)} messages")
        
        # Verify no toggle behavior and proper state
        issues = []
        
        # Check title was reset
        if conv_after_clear.title != "New Conversation":
            issues.append(f"❌ Title not reset: '{conv_after_clear.title}' != 'New Conversation'")
        
        # Check message count was reset
        if conv_after_clear.message_count != 0:
            issues.append(f"❌ Message count not reset: {conv_after_clear.message_count} != 0")
        
        # Check history is consistently empty (no toggle)
        history_lengths = [len(history_check_1), len(history_check_2), len(history_check_3)]
        if not all(length == 0 for length in history_lengths):
            issues.append(f"❌ History not consistently empty: {history_lengths}")
        
        # Check for toggle behavior
        if len(set(history_lengths)) > 1:
            issues.append(f"❌ Toggle behavior detected: varying lengths {history_lengths}")
        
        if not issues:
            print("✅ Clear Chat Display test PASSED - No toggle behavior, proper state reset")
            test_passed = True
        else:
            for issue in issues:
                print(issue)
            print("❌ Clear Chat Display test FAILED")
            test_passed = False
            
        # Cleanup
        new_sidekick.cleanup()
        return test_passed
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Cleanup
        if session_key in active_sidekicks:
            active_sidekicks[session_key].cleanup()
            del active_sidekicks[session_key]
        memory_manager.delete_conversation(conversation_id, username)

async def test_default_conversation_auto_titling():
    """Test that default conversations created at login get properly auto-titled"""
    print("\n🧪 Test 2: Default Conversation Auto-Titling")
    print("="*45)
    
    # Create a default conversation (simulating login)
    username = "test_user"
    default_conv_result = memory_manager.create_conversation(username)  # No custom title
    
    if not default_conv_result["success"]:
        print(f"❌ Failed to create default conversation: {default_conv_result}")
        return False
        
    conversation_id = default_conv_result["conversation_id"]
    print(f"📝 Created default conversation: {conversation_id}")
    
    # Verify it starts with default title
    conv_initial = memory_manager.get_conversation(conversation_id, username)
    print(f"📊 Initial state - Title: '{conv_initial.title}', Count: {conv_initial.message_count}")
    
    if conv_initial.title != "New Conversation":
        print(f"⚠️ Warning: Expected 'New Conversation', got '{conv_initial.title}'")
    
    # Create Sidekick instance (simulating normal setup)
    sidekick = Sidekick(username=username, conversation_id=conversation_id)
    await sidekick.setup()
    
    try:
        # Send first message (should trigger auto-titling)
        print("\n📤 Sending first message to trigger auto-titling")
        test_message = "Can you explain quantum computing and its applications in cryptography?"
        
        await sidekick.run_superstep(
            test_message, 
            "Provide a comprehensive explanation", 
            [], 
            original_message=test_message
        )
        
        # Check if conversation was auto-titled
        conv_after_message = memory_manager.get_conversation(conversation_id, username)
        print(f"📊 After message - Title: '{conv_after_message.title}', Count: {conv_after_message.message_count}")
        
        # Verify auto-titling worked
        issues = []
        
        if conv_after_message.title == "New Conversation":
            issues.append("❌ Title was not updated from default")
        
        if conv_after_message.message_count == 0:
            issues.append("❌ Message count was not incremented")
            
        if len(conv_after_message.title) > 60:
            issues.append(f"❌ Title too long: {len(conv_after_message.title)} chars")
        
        if not conv_after_message.title.startswith("Can you explain"):
            issues.append(f"❌ Title doesn't match message start: '{conv_after_message.title}'")
        
        if not issues:
            print("✅ Default conversation auto-titling test PASSED")
            test_passed = True
        else:
            for issue in issues:
                print(issue)
            print("❌ Default conversation auto-titling test FAILED")
            test_passed = False
            
        return test_passed
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Cleanup
        sidekick.cleanup()
        memory_manager.delete_conversation(conversation_id, username)

async def main():
    """Run all tests for Clear Chat Display and Auto-Titling fixes"""
    print("🧪 Starting Clear Chat Display & Auto-Titling Fix Tests")
    print("="*65)
    
    results = []
    
    # Run tests
    results.append(await test_clear_chat_display_no_toggle())
    results.append(await test_default_conversation_auto_titling())
    
    # Summary
    print("\n📊 Test Results Summary")
    print("="*30)
    passed = sum(results)
    total = len(results)
    
    print(f"✅ Passed: {passed}/{total}")
    print(f"❌ Failed: {total - passed}/{total}")
    
    if passed == total:
        print("\n🎉 All tests PASSED! Clear Chat Display and Auto-Titling fixes are working!")
    else:
        print(f"\n⚠️ {total - passed} test(s) FAILED. Issues need to be addressed.")
    
    return passed == total

if __name__ == "__main__":
    asyncio.run(main())