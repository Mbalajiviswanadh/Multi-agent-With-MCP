import os 
import certifi
from dotenv import load_dotenv

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from typing import TypedDict, Annotated
import operator
import uuid

import asyncio
import psycopg
from psycopg.rows import dict_row

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
)
from langchain_groq import ChatGroq
# from tools.tavily_tool import tavily_search
# from mymcp.mcp_client_test import tavily_mcp_search
from mymcp.mcp_client_main import tavily_mcp_search, aviation_mcp_call, extract_destination, forecast_mcp_search, weather_mcp_search
from tools.flight_tool import search_flights


def get_database_url():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError(
            "DATABASE_URL is missing. Please add your Render PostgreSQL External Database URL to .env"
        )

    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"

    return database_url


GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is missing. Please add it to your .env file.")


# =========================
# LLM
# =========================

llm = ChatGroq(
    model="openai/gpt-oss-120b",
    api_key=GROQ_API_KEY
)


# =========================
# State
# =========================

class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str
    flight_results: str
    hotel_results: str
    itinerary: str
    llm_calls: int
    weather_results:str


# =========================
# Flight Agent
# =========================

# def flight_agent(state: TravelState):
#     query = state["user_query"]
#     flight_data = search_flights(query)

#     return {
#         "flight_results": flight_data,
#         "messages": [
#             AIMessage(content="Flight results fetched.")
#         ],
#         "llm_calls": state.get("llm_calls", 0) + 1
#     }


# Flight Tool Router Prompt
FLIGHT_AGENT_PROMPT = """
You are a travel flight expert.

User Query:
{query}

Airport Information:
{airport_data}

Airline Information:
{airline_data}

Generate:

1. Likely departure airport
2. Likely arrival airport
3. Airlines serving this route
4. Typical flight duration
5. Estimated airfare range
6. Peak season pricing warning
7. Booking advice

Return concise travel guidance.
"""




# Flight Agent
def flight_agent(state: TravelState):
    print("\n" + "="*50)
    print("📍 [FLIGHT AGENT] Started")
    print("="*50)

    query = state["user_query"]
    print(f"User Query: {query}")

    try:
        airports = asyncio.run(
            aviation_mcp_call(
                "list_airports"
            )
        )

        airlines = asyncio.run(
            aviation_mcp_call(
                "list_airlines"
            )
        )

        print("\nAIRPORTS:", airports)
        print("\nAIRLINES:", airlines)

        prompt = FLIGHT_AGENT_PROMPT.format(
            query=query,
            airport_data=str(airports)[:3000],
            airline_data=str(airlines)[:3000]
        )

        response = llm.invoke([
            SystemMessage(
                content="You are an expert travel flight planner."
            ),
            HumanMessage(content=prompt)
        ])

        flight_data = response.content
        print("✅ [FLIGHT AGENT] Flight guidance generated successfully")

    except Exception as e:
        print(f"❌ [FLIGHT AGENT] Error: {e}")
        flight_data = f"Flight information unavailable: {str(e)}"

    return {
        "flight_results": flight_data,
        "messages": [
            AIMessage(
                content="Flight recommendations generated"
            )
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }



# =========================
# Hotel Agent
# =========================

def hotel_agent(state: TravelState):
    print("\n" + "="*50)
    print("🏨 [HOTEL AGENT] Started")
    print("="*50)

    query = f"Best hotels for {state['user_query']}"
    print(f"Hotel Search Query: {query}")

    try:
        hotel_results = asyncio.run(tavily_mcp_search(query))
        print(f"\nHOTEL RESULTS (snippet): {str(hotel_results)[:400]}...")
        print("✅ [HOTEL AGENT] Hotels fetched successfully")
    except Exception as e:
        print(f"❌ [HOTEL AGENT] Error: {e}")
        hotel_results = f"Hotel information unavailable: {str(e)}"

    return {
        "hotel_results": hotel_results,
        "messages": [
            AIMessage(content="Hotel information fetched.")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


# =========================
# Weather Agent
# =========================

def weather_agent(state: TravelState):
    print("\n" + "="*50)
    print("☀️ [WEATHER AGENT] Started")
    print("="*50)

    try:
        city = extract_destination(state["user_query"])
        print(f"Extracted City: {city}")

        weather_data = asyncio.run(
            weather_mcp_search(city)
        )
        print(f"\nCURRENT WEATHER: {weather_data}")

        forecast_data = asyncio.run(
            forecast_mcp_search(city)
        )
        print(f"\nFORECAST: {forecast_data}")

        weather_results = f"""
        Current Weather for {city}:
        {weather_data}

        Forecast for {city}:
        {forecast_data}
        """
        print("✅ [WEATHER AGENT] Weather & Forecast fetched successfully")
    except Exception as e:
        print(f"❌ [WEATHER AGENT] Error: {e}")
        weather_results = f"Live weather data currently unavailable: {str(e)}"

    return {
        "weather_results": weather_results,
        "messages": [
            AIMessage(
                content="Weather information fetched"
            )
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }



# =========================
# Itinerary Agent
# =========================

def itinerary_agent(state: TravelState):
    print("\n" + "="*50)
    print("🗺️ [ITINERARY AGENT] Started")
    print("="*50)

    flight_info = str(state.get("flight_results", ""))[:2000]
    hotel_info = str(state.get("hotel_results", ""))[:2500]
    weather_info = str(state.get("weather_results", ""))[:1500]

    prompt = f"""
Create a complete travel itinerary.

User Query:
{state['user_query']}

Flight Results:
{flight_info}

Hotel Results:
{hotel_info}

Weather Results:
{weather_info}

Make the itinerary practical, budget-aware, and easy to follow.
"""

    response = llm.invoke([
        SystemMessage(content="You are an expert travel planner."),
        HumanMessage(content=prompt)
    ])

    print("✅ [ITINERARY AGENT] Itinerary generated successfully")

    return {
        "itinerary": response.content,
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


# =========================
# Final Response Agent
# =========================

def final_agent(state: TravelState):
    print("\n" + "="*50)
    print("📋 [FINAL AGENT] Started")
    print("="*50)

    flight_info = str(state.get("flight_results", ""))[:2000]
    hotel_info = str(state.get("hotel_results", ""))[:2500]
    weather_info = str(state.get("weather_results", ""))[:1500]
    itinerary_info = str(state.get("itinerary", ""))[:3000]

    final_prompt = f"""
Generate the final travel response for the user.

User Request:
{state['user_query']}

Flights:
{flight_info}

Hotels:
{hotel_info}

Weather:
{weather_info}

Itinerary:
{itinerary_info}

Format the final answer beautifully using these sections:

1. Trip Summary
2. Flight Information
3. Hotel Suggestions
4. Weather Information
5. Day-by-Day Itinerary
6. Estimated Budget
7. Final Recommendations


Important:
- Be clear and practical.
- Mention that live flight API may not provide ticket prices if pricing is unavailable.
- Include weather-based travel advice.
- Keep the response useful for real travel planning.
"""

    response = llm.invoke([
        SystemMessage(content="You are a professional AI travel booking assistant."),
        HumanMessage(content=final_prompt)
    ])

    print("✅ [FINAL AGENT] Final travel guide generated successfully")
    print("="*50 + "\n")

    return {
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


# =========================
# Build Graph
# =========================


graph = StateGraph(TravelState)

graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("weather_agent", weather_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("final_agent", final_agent)

graph.add_edge(START, "flight_agent")
graph.add_edge("flight_agent", "hotel_agent")
graph.add_edge("hotel_agent", "weather_agent")
graph.add_edge("weather_agent", "itinerary_agent")
graph.add_edge("itinerary_agent", "final_agent")
graph.add_edge("final_agent", END)

# =========================
# PostgreSQL Checkpointer
# =========================
DATABASE_URL = get_database_url()

_conn = psycopg.connect(
    DATABASE_URL,
    autocommit=True,
    row_factory=dict_row
)

checkpointer = PostgresSaver(_conn)
checkpointer.setup()

travel_graph = graph.compile(checkpointer=checkpointer)



# =========================
# Function for FastAPI
# =========================

def run_travel_agent(user_input: str, thread_id: str | None = None):
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    result = travel_graph.invoke(
        {
            "messages": [
                HumanMessage(content=user_input)
            ],
            "user_query": user_input,
            "flight_results": "",
            "hotel_results": "",
            "weather_results":"",
            "itinerary": "",
            "llm_calls": 0
        },
        config=config
    )

    final_answer = result["messages"][-1].content

    return {
        "thread_id": thread_id,
        "answer": final_answer,
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "weather_results": result.get("weather_results", ""),
        "itinerary": result.get("itinerary", ""),
        "llm_calls": result.get("llm_calls", 0),
    }
