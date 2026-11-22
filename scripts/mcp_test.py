# from mcp.mcp_client_test import get_all_tools, tavily_mcp_search
from mymcp.mcp_client_main import get_all_tools

import asyncio

if __name__ == "__main__":
    # query="latest news about AI"
    asyncio.run(get_all_tools())
    # asyncio.run(tavily_mcp_search(query))

