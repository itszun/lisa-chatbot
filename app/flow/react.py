from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

load_dotenv()

@tool
def multiply(a: int, b: int) -> int:
    """
    To multiply between two numbers (a = first number, b = second number)
    """
    return a * b

tools = [
    multiply,
]


llm = ChatOpenAI(model="gpt-4.1-mini").bind_tools(tools)