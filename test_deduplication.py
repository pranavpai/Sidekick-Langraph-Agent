#!/usr/bin/env python3
"""
Test script to verify message deduplication works properly
Tests that duplicate assistant messages are not shown to users
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from memory_manager import memory_manager
from sidekick import Sidekick

async def test_message_deduplication():
    """Test that message deduplication prevents duplicate assistant responses"""
    print("\n🧪 Test: Message Deduplication")
    print("="*40)
    
    # Create a test conversation
    username = "test_user"
    test_conv_result = memory_manager.create_conversation(username, "Test Deduplication")
    
    if not test_conv_result["success"]:
        print(f"❌ Failed to create test conversation: {test_conv_result}")
        return False
        
    conversation_id = test_conv_result["conversation_id"]
    print(f"📝 Created test conversation: {conversation_id}")
    
    # Create a sidekick instance
    sidekick = Sidekick(username=username, conversation_id=conversation_id)
    await sidekick.setup()
    
    try:
        # Step 1: Send first message and get response
        print("\n📤 Step 1: Sending first message")
        first_result = await sidekick.run_superstep(
            "What is the capital of France?", 
            "Provide a simple answer", 
            [],  # Empty history
            original_message="What is the capital of France?"
        )
        
        print(f"📊 First result length: {len(first_result)}")
        for i, msg in enumerate(first_result):
            print(f"  {i+1}. [{msg['role']}]: {msg['content'][:60]}...")
        
        # Step 2: Load conversation history (simulating switching back to this conversation)
        print("\n📚 Step 2: Loading conversation history")
        loaded_history = await sidekick.get_conversation_history()
        print(f"📊 Loaded history length: {len(loaded_history)}")
        for i, msg in enumerate(loaded_history):
            print(f"  {i+1}. [{msg['role']}]: {msg['content'][:60]}...")
        
        # Step 3: Send second message with loaded history (this should trigger deduplication)
        print("\n📤 Step 3: Sending second message with loaded history")
        second_result = await sidekick.run_superstep(
            "What is the population of Paris?", 
            "Provide a simple answer", 
            loaded_history,  # Pass loaded history
            original_message="What is the population of Paris?"
        )
        
        print(f"📊 Second result length: {len(second_result)}")
        for i, msg in enumerate(second_result):
            print(f"  {i+1}. [{msg['role']}]: {msg['content'][:60]}...")
        
        # Step 4: Analyze for duplicates
        print("\n🔍 Step 4: Analyzing for duplicates")
        
        # Count occurrences of each message content
        message_counts = {}
        for msg in second_result:
            content = msg['content'].strip()
            if content in message_counts:
                message_counts[content] += 1
            else:
                message_counts[content] = 1
        
        # Check for duplicates
        duplicates_found = []
        for content, count in message_counts.items():
            if count > 1:
                duplicates_found.append(f"'{content[:50]}...' appears {count} times")
        
        if duplicates_found:
            print("❌ DUPLICATES FOUND:")
            for duplicate in duplicates_found:
                print(f"  • {duplicate}")
            test_passed = False
        else:
            print("✅ NO DUPLICATES FOUND - Test PASSED")
            test_passed = True
        
        # Additional check: ensure we have reasonable conversation flow
        if len(second_result) < 4:  # Should have at least 2 user + 2 assistant messages
            print(f"⚠️ Warning: Expected at least 4 messages, got {len(second_result)}")
        
        # Check message alternation (user -> assistant -> user -> assistant)
        role_pattern = [msg['role'] for msg in second_result]
        print(f"📋 Message pattern: {' -> '.join(role_pattern)}")
        
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

async def test_direct_deduplication_method():
    """Test the _merge_conversation_with_deduplication method directly"""
    print("\n🧪 Test: Direct Deduplication Method")
    print("="*45)
    
    # Create a sidekick instance for testing
    sidekick = Sidekick()
    
    try:
        # Test scenario: existing history with some messages
        existing_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there! How can I help you today?"},
            {"role": "user", "content": "What is AI?"},
            {"role": "assistant", "content": "AI stands for Artificial Intelligence..."}
        ]
        
        # Test 1: Adding genuinely new messages (should be added)
        print("\n🧪 Test 1: Adding new messages")
        new_user = {"role": "user", "content": "Tell me about machine learning"}
        new_assistant = {"role": "assistant", "content": "Machine learning is a subset of AI..."}
        
        result1 = sidekick._merge_conversation_with_deduplication(
            existing_history, new_user, new_assistant
        )
        
        print(f"📊 Result 1 length: {len(result1)} (expected: 6)")
        expected_length_1 = len(existing_history) + 2
        if len(result1) == expected_length_1:
            print("✅ Test 1 PASSED - New messages added correctly")
        else:
            print(f"❌ Test 1 FAILED - Expected {expected_length_1}, got {len(result1)}")
        
        # Test 2: Adding duplicate messages (should be skipped)
        print("\n🧪 Test 2: Adding duplicate messages")
        duplicate_user = {"role": "user", "content": "Hello"}  # Exact duplicate
        duplicate_assistant = {"role": "assistant", "content": "Hi there! How can I help you today?"}  # Exact duplicate
        
        result2 = sidekick._merge_conversation_with_deduplication(
            existing_history, duplicate_user, duplicate_assistant
        )
        
        print(f"📊 Result 2 length: {len(result2)} (expected: {len(existing_history)})")
        if len(result2) == len(existing_history):
            print("✅ Test 2 PASSED - Duplicate messages correctly skipped")
        else:
            print(f"❌ Test 2 FAILED - Expected {len(existing_history)}, got {len(result2)}")
        
        # Test 3: Adding one new, one duplicate (mixed scenario)
        print("\n🧪 Test 3: Mixed new and duplicate messages")
        mixed_user = {"role": "user", "content": "What is AI?"}  # Duplicate
        mixed_assistant = {"role": "assistant", "content": "This is a completely new response"}  # New
        
        result3 = sidekick._merge_conversation_with_deduplication(
            existing_history, mixed_user, mixed_assistant
        )
        
        print(f"📊 Result 3 length: {len(result3)} (expected: {len(existing_history) + 1})")
        expected_length_3 = len(existing_history) + 1  # Only assistant message should be added
        if len(result3) == expected_length_3:
            print("✅ Test 3 PASSED - Mixed scenario handled correctly")
        else:
            print(f"❌ Test 3 FAILED - Expected {expected_length_3}, got {len(result3)}")
        
        # Summary
        all_passed = (
            len(result1) == expected_length_1 and
            len(result2) == len(existing_history) and
            len(result3) == expected_length_3
        )
        
        return all_passed
        
    except Exception as e:
        print(f"❌ Direct method test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all deduplication tests"""
    print("🧪 Starting Message Deduplication Tests")
    print("="*50)
    
    results = []
    
    # Run tests
    results.append(await test_direct_deduplication_method())
    results.append(await test_message_deduplication())
    
    # Summary
    print("\n📊 Test Results Summary")
    print("="*30)
    passed = sum(results)
    total = len(results)
    
    print(f"✅ Passed: {passed}/{total}")
    print(f"❌ Failed: {total - passed}/{total}")
    
    if passed == total:
        print("\n🎉 All deduplication tests PASSED! No more duplicate messages.")
    else:
        print(f"\n⚠️ {total - passed} test(s) FAILED. Duplication issues remain.")
    
    return passed == total

if __name__ == "__main__":
    asyncio.run(main())