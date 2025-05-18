from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import AzureOpenAI
import re
import requests
from typing import List
class AIClient:
    """Azure OpenAI client wrapper with additional functionality"""
    
    def __init__(self, api_key: str, endpoint: str, deployment: str):
        self.client = AzureOpenAI(
            api_key=api_key,
            api_version="2023-07-01-preview",
            azure_endpoint=endpoint
        )
        self.deployment = deployment
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((requests.exceptions.RequestException, TimeoutError))
    )
    def analyze_text(self, system_prompt: str, user_content: str, 
                    temperature: float = 0.3, json_response: bool = False) -> str:
        """Make a request to the AI model with retry logic"""
        kwargs = {
            "model": self.deployment,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": temperature,
        }
        
        if json_response:
            kwargs["response_format"] = {"type": "json_object"}
        
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
    
    def chunk_analyze(self, system_prompt: str, content: str, max_chunk_size: int = 25000,
                     temperature: float = 0.3, json_response: bool = False) -> List[str]:
        """Break content into chunks for analysis if needed"""
        if len(content) <= max_chunk_size:
            return [self.analyze_text(system_prompt, content, temperature, json_response)]
        
        # If content is too large, split it into chunks and analyze each chunk
        chunks = self._split_content(content, max_chunk_size)
        results = []
        
        for i, chunk in enumerate(chunks):
            chunk_context = f"CHUNK {i+1} OF {len(chunks)}:\n\n{chunk}"
            results.append(self.analyze_text(system_prompt, chunk_context, temperature, json_response))
            
        return results
    
    def _split_content(self, content: str, max_size: int) -> List[str]:
        """Split content into reasonably-sized chunks, trying to break at file boundaries"""
        chunks = []
        current_chunk = ""
        
        # Try to split on file boundaries (diff headers)
        file_sections = re.split(r"(diff --git .*?\n)", content, flags=re.DOTALL)
        
        for section in file_sections:
            if len(current_chunk) + len(section) <= max_size:
                current_chunk += section
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = section
                
        if current_chunk:
            chunks.append(current_chunk)
            
        # If chunks are still too large, split them further
        result = []
        for chunk in chunks:
            if len(chunk) <= max_size:
                result.append(chunk)
            else:
                # Fall back to simple chunking
                for i in range(0, len(chunk), max_size):
                    result.append(chunk[i:i + max_size])
        
        return result
