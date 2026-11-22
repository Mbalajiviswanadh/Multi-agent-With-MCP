import os
import asyncio
import certifi
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

load_dotenv()


# flow:
# MCP_CLIENT (1)
# MCP_SERVER (2)
# APIKEYS (3)
# TOOLS (4)

# mcp's API KEY (3)
TAVILY_API_KEY=os.getenv("TAVILY_API_KEY")

# inside this we have to mention all of the mcp remote servers
client = MultiServerMCPClient(   # this is mcp client (1)

    {
        # this is mcp server (2)
        "tavily":{
            "transport":"streamable_http",
            "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={TAVILY_API_KEY}"
        }
    }
)


# these are mcp server tools (4)
async def get_all_tools():
    tools = await client.get_tools()
    
    print("\nAvailable MCP Tools:\n")

    for tool in tools:
        print(tool.name)

# This retuns only tavily_search tool object
tavily_search_tool = None

async def get_tavily_search_tool():
    global tavily_search_tool
    if tavily_search_tool is not None:
        return

    tools = await client.get_tools()
    print("\nAvailable MCP Tools:")

    for tool in tools:
        print(tool.name)

    tavily_search_tool = next(
        tool
        for tool in tools
        if tool.name == "tavily_search"
    )

# This function can be used to call the tavily_search tool with a query in backend.py
async def tavily_mcp_search(query: str):
    await get_tavily_search_tool()
    result = await tavily_search_tool.ainvoke(
        {
            "query": query
        }
    )
    return result
    # print(result)