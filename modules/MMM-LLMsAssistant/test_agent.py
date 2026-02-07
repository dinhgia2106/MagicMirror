#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for Agent Tools with Gemini Function Calling
"""

import json
import os
import sys

# Setup UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_tools import AgentTools, get_gemini_tools, TOOL_DECLARATIONS


def test_with_gemini():
    """Test function calling with actual Gemini API"""
    try:
        import google.generativeai as genai
        
        # Use API key from environment or config
        api_key = os.environ.get("GEMINI_API_KEY", "AIzaSyDN2UflL1lg8Si_-Fh0zOXHBAYqZXK85Bc")
        genai.configure(api_key=api_key)
        
        # Initialize tools
        tools = AgentTools({
            "holiday_api_url": "http://192.168.1.11:8000/api/holidays",
            "lat": 16.463713,
            "lon": 107.590866,
            "timezone": "Asia/Ho_Chi_Minh"
        })
        
        # System instruction
        system_instruction = """You are Lens, a smart Vietnamese personal assistant. 
You have access to tools to get current date/time, weather, and holiday information.
IMPORTANT RULES:
- Always respond in Vietnamese
- Do NOT use markdown formatting
- Keep responses concise
- When user asks about time, date, weather, or holidays, USE THE APPROPRIATE TOOL first"""

        # Create model with tools
        model = genai.GenerativeModel(
            'gemini-2.5-flash',
            tools=[get_gemini_tools()],
            system_instruction=system_instruction
        )
        
        # Test queries
        test_queries = [
            "May gio roi?",
            "Thoi tiet hom nay the nao?",
            "Sap toi co ngay le gi khong?",
            "Ngay mai la thu may?",
            "Du bao thoi tiet 3 ngay toi?"
        ]
        
        print("=" * 60)
        print("TESTING GEMINI FUNCTION CALLING WITH AGENT TOOLS")
        print("=" * 60)
        
        for query in test_queries:
            print(f"\n>>> Query: {query}")
            print("-" * 40)
            
            # Start chat
            chat = model.start_chat(enable_automatic_function_calling=False)
            response = chat.send_message(query)
            
            # Check for function calls
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                
                function_calls = []
                text_parts = []
                
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            function_calls.append(part.function_call)
                        elif hasattr(part, 'text') and part.text:
                            text_parts.append(part.text)
                
                if function_calls:
                    print(f"Function calls detected: {len(function_calls)}")
                    
                    function_responses = []
                    for fc in function_calls:
                        tool_name = fc.name
                        tool_args = dict(fc.args) if fc.args else {}
                        
                        print(f"  - Calling: {tool_name}({tool_args})")
                        
                        # Execute tool
                        result = tools.execute_tool(tool_name, tool_args)
                        print(f"  - Result: {json.dumps(result, ensure_ascii=False)[:150]}...")
                        
                        function_responses.append({
                            "name": tool_name,
                            "response": result
                        })
                    
                    # Send results back to Gemini
                    function_response_parts = []
                    for fr in function_responses:
                        function_response_parts.append(
                            genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=fr["name"],
                                    response={"result": json.dumps(fr["response"], ensure_ascii=False)}
                                )
                            )
                        )
                    
                    final_response = chat.send_message(function_response_parts)
                    
                    if final_response.candidates and len(final_response.candidates) > 0:
                        final_text = ""
                        for part in final_response.candidates[0].content.parts:
                            if hasattr(part, 'text') and part.text:
                                final_text += part.text
                        print(f"\n>>> Lens: {final_text}")
                
                elif text_parts:
                    print(f">>> Lens: {' '.join(text_parts)}")
            
            print()
        
        print("=" * 60)
        print("TEST COMPLETED SUCCESSFULLY")
        print("=" * 60)
        
    except ImportError as e:
        print(f"Import error: {e}")
        print("Please install: pip install google-generativeai")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_with_gemini()
