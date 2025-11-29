from pydantic import BaseModel  

class QueryRequest(BaseModel):  
    query: str  

class BookResponse(BaseModel):  
    isbn: str  
    title: str  
    author: str  
    tags: list[str]  