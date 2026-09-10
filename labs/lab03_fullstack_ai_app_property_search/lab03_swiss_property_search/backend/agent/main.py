import os
from typing import Any, Optional
from fastapi import FastAPI
from pydantic import BaseModel
from agent import get_agent

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Configure CORS
ALLOWED_ORIGINS_STR = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS_STR.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Session Service
session_service = InMemorySessionService()

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default_session"
    backend: str = "alloydb"

class ChatResponse(BaseModel):
    response: str
    tool_details: Optional[Any] = None
    used_prompt: Optional[str] = None

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        user_id = "default_user"
        session_id = request.session_id
        app_name = f"property_agent_{request.backend}"
        
        dynamic_agent = get_agent(request.backend)
        runner = Runner(agent=dynamic_agent, app_name=app_name, session_service=session_service)
        
        session = await session_service.get_session(app_name=app_name, user_id=user_id, session_id=session_id)
        if not session:
            await session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id)
        
        response_text = ""
        tool_details = None
        used_prompt = None
        
        from google.genai.types import Content, Part
        import json
        
        message = Content(role="user", parts=[Part(text=request.message)])
        
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=message
        ):
            print(f"DEBUG: Received event type: {type(event)}")
            
            # Capture Tool Call
            if hasattr(event, 'tool_call') and event.tool_call:
                print("DEBUG: Found tool_call in event")
                if hasattr(event.tool_call, 'function_calls'):
                    for fc in event.tool_call.function_calls:
                        if 'prompt' in fc.args:
                            used_prompt = fc.args['prompt']
                            print(f"DEBUG: Captured tool prompt: {used_prompt}")

            # Capture Tool Response
            if hasattr(event, 'tool_response') and event.tool_response:
                 print("DEBUG: Found tool_response in event")
                 if hasattr(event.tool_response, 'function_responses'):
                    for fr in event.tool_response.function_responses:
                        try:
                            print(f"DEBUG: Processing function response: {fr.name}")
                            response_payload = fr.response
                            print(f"DEBUG: Raw response payload type: {type(response_payload)}")
                            
                            if isinstance(response_payload, dict):
                                if 'result' in response_payload:
                                     tool_details = response_payload['result']
                                else:
                                     tool_details = response_payload
                                
                                if isinstance(tool_details, str):
                                    try:
                                        tool_details = json.loads(tool_details)
                                    except Exception:
                                        pass

                            elif isinstance(response_payload, str):
                                try:
                                    tool_details = json.loads(response_payload)
                                except Exception:
                                    tool_details = response_payload
                                
                            print(f"DEBUG: Captured tool details: {type(tool_details)}")
                        except Exception as e:
                            print(f"DEBUG: Failed to parse tool response: {e}")

            # Extract text response
            if hasattr(event, 'content') and event.content:
                for part in event.content.parts or []:
                    if part.text:
                        response_text += part.text
            elif hasattr(event, 'text') and event.text:
                response_text += event.text
            
        print(f"DEBUG: Final response text: {response_text}")
        return ChatResponse(
            response=response_text or "Agent executed (no text response)",
            tool_details=tool_details,
            used_prompt=used_prompt
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return ChatResponse(response=f"I encountered an issue processing your request: {str(e)}")

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
