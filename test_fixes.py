#!/usr/bin/env python3
"""
Test script to verify conversation management fixes work properly
Tests the three main issues without requiring the Gradio UI
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from memory_manager import memory_manager
from sidekick import Sidekick

async def test_conversation_history_filtering():
    """Test that conversation history filtering removes duplicates and internal messages"""
    print("\n🧪 Test 1: Conversation History Filtering")
    print("="*50)
    
    # Create a test sidekick instance
    sidekick = Sidekick(username="test_user", conversation_id="test_conv_history")
    await sidekick.setup()
    
    # Simulate a conversation with clarifying questions (should be filtered out)
    test_message = "Please give a pdf report on taj mahal\n\nClarifying Questions and Answers:\nQ1: What format? A1: PDF\nQ2: What details? A2: Architecture"
    
    try:
        # Process the message (this will create checkpoints with internal messages)
        result = await sidekick.run_superstep(
            test_message, 
            "Create a comprehensive report", 
            [], 
            original_message="Please give a pdf report on taj mahal"
        )
        
        # Get conversation history and check filtering
        history = await sidekick.get_conversation_history()
        
        print(f"📊 History length: {len(history)}")
        for i, msg in enumerate(history):
            print(f"  {i+1}. [{msg['role']}]: {msg['content'][:100]}...")
            
        # Check for issues
        issues = []
        for msg in history:
            if "Clarifying Questions and Answers" in msg['content']:
                issues.append("❌ Found clarifying questions in history")
            if msg['content'].startswith("Evaluator Feedback"):
                issues.append("❌ Found evaluator feedback in history")
            if msg['content'].startswith("Planning Phase"):
                issues.append("❌ Found planning phase in history")
                
        if not issues:
            print("✅ History filtering test PASSED")
        else:
            for issue in issues:
                print(issue)
            print("❌ History filtering test FAILED")
            
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    # Cleanup
    sidekick.cleanup()
    return len(issues) == 0

async def test_clear_conversation_functionality():
    """Test that clear conversation actually clears the database"""
    print("\n🧪 Test 2: Clear Conversation Functionality")
    print("="*50)
    
    # Create a test conversation
    username = "test_user"
    test_conv_result = memory_manager.create_conversation(username, "Test Clear Conversation")
    
    if not test_conv_result["success"]:
        print(f"❌ Failed to create test conversation: {test_conv_result}")
        return False
        
    conversation_id = test_conv_result["conversation_id"]
    print(f"📝 Created test conversation: {conversation_id}")
    
    # Create a sidekick instance and add some messages
    sidekick = Sidekick(username=username, conversation_id=conversation_id)
    await sidekick.setup()
    
    try:
        # Add a test message to create some history
        await sidekick.run_superstep(
            "Test message for clearing", 
            "Simple test", 
            [], 
            original_message="Test message for clearing"
        )
        
        # Check history before clearing
        history_before = await sidekick.get_conversation_history()
        print(f"📊 History before clear: {len(history_before)} messages")
        
        # Clear the conversation
        clear_result = memory_manager.clear_conversation_history(conversation_id, username)
        print(f"🧹 Clear result: {clear_result}")
        
        if not clear_result["success"]:
            print("❌ Clear conversation test FAILED - clear operation failed")
            return False
            
        # Check history after clearing
        history_after = await sidekick.get_conversation_history()
        print(f"📊 History after clear: {len(history_after)} messages")
        
        if len(history_after) == 0:
            print("✅ Clear conversation test PASSED")
            test_passed = True
        else:
            print("❌ Clear conversation test FAILED - history still present")
            test_passed = False
            
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        test_passed = False
    
    # Cleanup
    sidekick.cleanup()
    memory_manager.delete_conversation(conversation_id, username)
    return test_passed

async def test_title_generation_and_message_counting():
    """Test that conversation titles and message counts update correctly"""
    print("\n🧪 Test 3: Title Generation and Message Counting")
    print("="*50)
    
    # Create a test conversation
    username = "test_user"
    test_conv_result = memory_manager.create_conversation(username)
    
    if not test_conv_result["success"]:
        print(f"❌ Failed to create test conversation: {test_conv_result}")
        return False
        
    conversation_id = test_conv_result["conversation_id"]
    thread_id = test_conv_result["thread_id"]
    print(f"📝 Created test conversation: {conversation_id}")
    
    # Check initial state
    conv_before = memory_manager.get_conversation(conversation_id, username)
    print(f"📊 Initial title: '{conv_before.title}', messages: {conv_before.message_count}")
    
    try:
        # Test auto-title generation
        test_message = "Can you help me understand machine learning algorithms and their applications?"
        auto_title_result = memory_manager.auto_title_conversation(conversation_id, username, test_message)
        print(f"🏷️ Auto-title result: {auto_title_result}")
        
        # Check title after auto-titling
        conv_after_title = memory_manager.get_conversation(conversation_id, username)
        print(f"📊 After title: '{conv_after_title.title}', messages: {conv_after_title.message_count}")
        
        # Test message count update
        message_update_result = memory_manager.update_conversation(conversation_id, username, increment_messages=True)
        print(f"📈 Message update result: {message_update_result}")
        
        # Check final state
        conv_final = memory_manager.get_conversation(conversation_id, username)
        print(f"📊 Final: '{conv_final.title}', messages: {conv_final.message_count}")
        
        # Verify changes
        issues = []
        if conv_after_title.title == "New Conversation":
            issues.append("❌ Title was not updated from default")
        if conv_final.message_count == 0:
            issues.append("❌ Message count was not incremented")
        if len(conv_after_title.title) > 60:
            issues.append("❌ Title is too long")
            
        if not issues:
            print("✅ Title generation and message counting test PASSED")
            test_passed = True
        else:
            for issue in issues:
                print(issue)
            print("❌ Title generation and message counting test FAILED")
            test_passed = False
            
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        test_passed = False
    
    # Cleanup
    memory_manager.delete_conversation(conversation_id, username)
    return test_passed

async def main():
    """Run all tests"""
    print("🧪 Starting Conversation Management Fix Tests")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(await test_conversation_history_filtering())
    results.append(await test_clear_conversation_functionality()) 
    results.append(await test_title_generation_and_message_counting())
    
    # Summary
    print("\n📊 Test Results Summary")
    print("="*30)
    passed = sum(results)
    total = len(results)
    
    print(f"✅ Passed: {passed}/{total}")
    print(f"❌ Failed: {total - passed}/{total}")
    
    if passed == total:
        print("\n🎉 All tests PASSED! Fixes are working correctly.")
    else:
        print(f"\n⚠️ {total - passed} test(s) FAILED. Issues need to be addressed.")
    
    return passed == total

if __name__ == "__main__":
    asyncio.run(main())