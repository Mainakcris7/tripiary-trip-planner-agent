import os
import serpapi
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import START, END, StateGraph
from scrapers.rail_info_scraper import scrape_trains
from agents.journey_info_extractor import get_trip_info_agent
from typing import TypedDict, Annotated, Optional, Literal, List, Dict
from pydantic import BaseModel
from langsmith import traceable
from langchain_tavily import TavilySearch
from datetime import datetime, timedelta
from prompts.system_prompts import MASTER_ITINERARY_PROMPT, TRAIN_DETAILS_PROMPT, FLIGHT_DETAILS_PROMPT, HOTEL_DETAILS_PROMPT, TRAVEL_GUIDE_PROMPT
from utils.data_extractor import extract_flights_data, extract_hotels_data

load_dotenv()

serpapi_client = serpapi.Client(api_key=os.environ['SERP_API_KEY'])

tavily_tool = TavilySearch(
    max_results=10,
    topic="general",
)


class AgentState(TypedDict):
    source: Annotated[str, 'Source of the trip']
    destination: Annotated[str, 'Destination of the trip']
    src_station_code: Optional[str]
    dest_station_code: Optional[str]
    src_airport_code: Optional[str]
    dest_airport_code: Optional[str]
    need_hotel_stay: Annotated[bool,
                               'Whether the user needs hotel stay during the trip'] = False
    journey_date: Annotated[str, 'Journey date in YYYY-MM-DD format']
    return_date: Annotated[Optional[str],
                           'Return date in YYYY-MM-DD format, if trip_mode == ROUND_TRIP, else None']
    outward_trains: Annotated[List[Dict],
                              'Raw train details from source to dest']
    return_trains: Annotated[List[Dict],
                             'Raw train details from destination to source']
    flights: Annotated[List[Dict], 'Raw flight details']
    hotels: Annotated[List[Dict], 'Raw hotel details']
    trip_mode: Literal['ROUND_TRIP', 'SINGLE_WAY'] = 'SINGLE_WAY'
    train_trip_details: Annotated[str, 'Train trip details options']
    flight_trip_details: Annotated[str, 'Flight trip details options']
    hotel_details: Annotated[str, 'Hotel details to stay']
    final_suggestion: Annotated[str,
                                'Final itinieary combining train, flight and hotel details']
    user_preferences: Annotated[Optional[str], 'User preferences for the trip']
    destination_research: Annotated[Optional[str],
                                    'Research about the destination city']
    total_members: int


train_llm = llm = ChatGoogleGenerativeAI(
    model='gemini-3.1-flash-lite'
)

flight_llm = llm = ChatGoogleGenerativeAI(
    model='gemini-3.1-flash-lite'
)

hotel_llm = llm = ChatGoogleGenerativeAI(
    model='gemini-3.1-flash-lite'
)

destination_research_llm = llm = ChatGoogleGenerativeAI(
    model='gemini-3.1-flash-lite'
)

itinerary_llm = llm = ChatGoogleGenerativeAI(
    model='gemini-3.5-flash',
    temperature=0.5
)


train_trip_prompt = ChatPromptTemplate.from_messages([
    ('system', TRAIN_DETAILS_PROMPT),
    ('user', 'Source: {source}\n Destination: {destination}\n Outward train data: {outward_train_data}\n Return train data: {return_train_data}\n User Preferences: {preferences}')
])

flight_trip_prompt = ChatPromptTemplate.from_messages([
    ('system', FLIGHT_DETAILS_PROMPT),
    ('user', 'Source: {source}\n Destination: {destination}\n Raw flight data: {flight_data}\n User Preferences: {preferences}\n Trip type: {trip_type}')
])

hotel_stay_prompt = ChatPromptTemplate.from_messages([
    ('system', HOTEL_DETAILS_PROMPT),
    ('user',
     'Destination: {destination}\n Raw hotel data: {hotel_data}\n User Preferences: {preferences}')
])

destination_research_prompt = ChatPromptTemplate.from_messages([
    ('system', TRAVEL_GUIDE_PROMPT),
    ('user', 'Source: {source}\n Destination: {destination}\n Journey date: {journey_date}\n Return date: {return_date}\n User preferences: {user_preferences}\n Tavily search results: {tavily_search_results}')
])

final_itinerary_prompt = ChatPromptTemplate.from_messages([
    ('system', MASTER_ITINERARY_PROMPT),
    ('user', 'Source: {source}\n Destination: {destination}\n Trip Type: {trip_type}\n Trip Members: {total_members}\n Journey Date: {journey_date}\n Return Date: {return_date}\n Train trip details: {train_trip_details}\n Flight trip details: {flight_trip_details}\n Hotel details: {hotel_details}\n Destination Research: {destination_research}\n User Preferences: {user_preferences}')
])

train_trip_chain = train_trip_prompt | train_llm | StrOutputParser()
flight_trip_chain = flight_trip_prompt | flight_llm | StrOutputParser()
hotel_stay_chain = hotel_stay_prompt | hotel_llm | StrOutputParser()
destination_research_chain = destination_research_prompt | destination_research_llm | StrOutputParser()
itinerary_chain = final_itinerary_prompt | itinerary_llm | StrOutputParser()

trip_info_agent = get_trip_info_agent()


@traceable(name="get_trip_codes", tags=["find_trip_codes"], metadata={"description": "Get station and airport codes for source and destination"})
def get_trip_codes(state: AgentState) -> AgentState:
    print('Getting trip codes for source and destination')
    output = trip_info_agent.invoke({
        'source': state['source'],
        'dest': state['destination']
    })
    print('Received trip codes:', output)
    return {
        'src_station_code': output.from_station_code,
        'dest_station_code': output.to_station_code,
        'src_airport_code': output.from_airport_code,
        'dest_airport_code': output.to_airport_code,
    }


@traceable(name="get_train_journey_options", tags=["find_train_journeys"], metadata={"description": "Get available train journey options for the specified route and dates"})
def get_train_journey_options(state: AgentState) -> AgentState:
    if not state['src_station_code'] or not state['dest_station_code']:
        return state
    print('Getting train journey options')
    going_train_details = scrape_trains(
        from_code=state['src_station_code'],
        to_code=state['dest_station_code'],
        journey_date=state['journey_date']
    )

    returning_train_details = []

    if state['trip_mode'] == 'ROUND_TRIP':
        returning_train_details = scrape_trains(
            from_code=state['dest_station_code'],
            to_code=state['src_station_code'],
            journey_date=state['return_date']
        )

    print('Received train details for outward journey:', len(going_train_details))
    print('Received train details for return journey:',
          len(returning_train_details))
    return {
        'outward_trains': going_train_details,
        'return_trains': returning_train_details
    }


@traceable(name="get_flight_journey_options", tags=["find_flight_journeys"], metadata={"description": "Get available flight journey options for the specified route and dates"})
def get_flight_journey_options(state: AgentState) -> AgentState:
    if not state['src_airport_code'] or not state['dest_airport_code']:
        return state
    print('Getting flight journey options')
    search_params = {
        "documentation_path": "/google-flights-api",
        "engine": "google_flights",
        "departure_id": state['src_airport_code'],
        "arrival_id": state['dest_airport_code'],
        "outbound_date": state['journey_date'],
        "adults": state['total_members'],
        "currency": "INR",
        "deep_search": "true",
        "type": "1" if state['trip_mode'] == 'ROUND_TRIP' else "2"
    }

    if state['trip_mode'] == 'ROUND_TRIP':
        search_params['type'] = '1'
        search_params['return_date'] = state['return_date']

    try:
        print('Searching for flight options...')
        flights = serpapi_client.search(search_params)
        flights_cleaned = extract_flights_data(flights)

        print('Received flight options:', len(flights_cleaned))

        return {
            'flights': flights_cleaned
        }
    except Exception as e:
        print('Error extracting flight data:', e)
        return {
            'flights': []
        }


@traceable(name="get_hotel_options", tags=["find_hotels"], metadata={"description": "Get available hotel options for the specified destination and dates"})
def get_hotel_options(state: AgentState) -> AgentState:

    if not state['need_hotel_stay']:
        return state

    print('Getting hotel options')
    search_prams = {
        "documentation_path": "/google-hotels-api",
        "engine": "google_hotels",
        "q": f"Best hotels and resorts in {state['destination']}",
        "hl": "en",
        "check_in_date": state['journey_date'],
        "adults": state['total_members'],
        "currency": "INR"
    }
    return_date = state.get('return_date')
    if return_date:
        search_prams["check_out_date"] = return_date
    else:  # If return date is not provided, set check-out date to one day after check-in date to get relevant hotel options for at least one night stay
        next_date = (datetime.strptime(
            state['journey_date'], '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        search_prams["check_out_date"] = next_date

    try:
        print('Searching for hotel options...')
        hotels_raw = serpapi_client.search(search_prams)
        print('Received hotel options:', len(hotels_raw.get('properties', [])))
        return {
            'hotels': extract_hotels_data(hotels_raw)
        }
    except Exception as e:
        print('Error extracting hotel data:', e)
        return {
            'hotels': []
        }


@traceable(name="get_destination_research", tags=["find_destination_research"], metadata={"description": "Get destination research information from Tavily"})
def get_destination_research(state: AgentState) -> AgentState:
    print('Getting destination research from Tavily')

    journey_month = datetime.strptime(
        state['journey_date'], '%Y-%m-%d').strftime('%B')

    query = f"""
Best places to visit, top tourist attractions, hidden gems, local experiences,
food, nightlife, adventure activities, cultural spots, family-friendly places,
travel tips, ideal sightseeing areas, and how to plan a practical few-day
trip in {state['destination']}.
Include realistic and popular recommendations suitable for tourists visiting during {journey_month}.
"""
    tavily_results = tavily_tool.invoke(query)
    print('Received Tavily results')

    destination_research = destination_research_chain.invoke({
        'source': state['source'],
        'destination': state['destination'],
        'journey_date': state['journey_date'],
        'return_date': state.get('return_date'),
        'user_preferences': state.get('user_preferences', ''),
        'tavily_search_results': tavily_results
    })
    print('Generated destination research from LLM')
    return {
        'destination_research': destination_research
    }


@traceable(name="get_train_trip_details", tags=["find_train_trips"], metadata={"description": "Get detailed train trip information from LLM"})
def get_train_trip_details(state: AgentState) -> AgentState:
    if not state['src_station_code'] or not state['dest_station_code']:
        return state
    print('Getting train trip details from LLM')
    result = train_trip_chain.invoke({
        'source': state['source'],
        'destination': state['destination'],
        'outward_train_data': state['outward_trains'],
        'return_train_data': state['return_trains'],
        'trip_type': state['trip_mode'],
        'preferences': state.get('user_preferences', '')
    })
    print('Received train trip details from LLM')
    return {'train_trip_details': result}


@traceable(name="get_flight_trip_details", tags=["find_flight_trips"], metadata={"description": "Get detailed flight trip information from LLM"})
def get_flight_trip_details(state: AgentState) -> AgentState:
    if not state['src_airport_code'] or not state['dest_airport_code']:
        return state
    print('Getting flight trip details from LLM')

    result = flight_trip_chain.invoke({
        'source': state['source'],
        'destination': state['destination'],
        'flight_data': state['flights'],
        'trip_type': state['trip_mode'],
        'preferences': state.get('user_preferences', '')
    })
    print('Received flight trip details from LLM')

    return {'flight_trip_details': result}


@traceable(name="get_hotel_details", tags=["find_hotel_details"], metadata={"description": "Get detailed hotel information from LLM"})
def get_hotel_details(state: AgentState) -> AgentState:
    if not state['need_hotel_stay']:
        return {
            'hotel_details': 'HOTEL_SEARCH_RESULT: NOT_NEEDED (USER DOES NOT NEED HOTEL STAY)'
        }
    print('Getting hotel details from LLM')

    result = hotel_stay_chain.invoke({
        'destination': state['destination'],
        'hotel_data': state['hotels'],
        'preferences': state.get('user_preferences', '')
    })
    print('Received hotel details from LLM')
    return {'hotel_details': result}


@traceable(name="get_final_itinerary", tags=["create_itinerary"], metadata={"description": "Create the final trip itinerary from all available information"})
def get_final_itinerary(state: AgentState) -> AgentState:
    print('Combining all details to create final itinerary')
    final_plan = itinerary_chain.invoke({
        'source': state['source'],
        'destination': state['destination'],
        'trip_type': state['trip_mode'],
        'total_members': state['total_members'],
        'journey_date': state['journey_date'],
        'return_date': state.get('return_date', ''),
        'train_trip_details': state.get('train_trip_details', ''),
        'flight_trip_details': state.get('flight_trip_details', ''),
        'hotel_details': state.get('hotel_details', ''),
        'destination_research': state.get('destination_research', ''),
        'user_preferences': state.get('user_preferences', '')
    })
    print('Final itinerary created')
    return {'final_suggestion': final_plan}


graph = StateGraph(AgentState)

graph.add_node('get_trip_codes', get_trip_codes)
graph.add_node('get_train_journey_options', get_train_journey_options)
graph.add_node('get_flight_journey_options', get_flight_journey_options)
graph.add_node('get_hotel_options', get_hotel_options)
graph.add_node('get_train_trip_details', get_train_trip_details)
graph.add_node('get_flight_trip_details', get_flight_trip_details)
graph.add_node('get_hotel_details', get_hotel_details)
graph.add_node('get_final_itinerary', get_final_itinerary)
graph.add_node('get_destination_research', get_destination_research)

graph.add_edge(START, 'get_trip_codes')
graph.add_edge('get_trip_codes', 'get_train_journey_options')
graph.add_edge('get_trip_codes', 'get_flight_journey_options')
graph.add_edge('get_trip_codes', 'get_hotel_options')
graph.add_edge('get_train_journey_options', 'get_train_trip_details')
graph.add_edge('get_trip_codes', 'get_destination_research')
graph.add_edge('get_flight_journey_options', 'get_flight_trip_details')
graph.add_edge('get_hotel_options', 'get_hotel_details')
graph.add_edge('get_train_trip_details', 'get_final_itinerary')
graph.add_edge('get_flight_trip_details', 'get_final_itinerary')
graph.add_edge('get_hotel_details', 'get_final_itinerary')
graph.add_edge('get_destination_research', 'get_final_itinerary')
graph.add_edge('get_final_itinerary', END)

agent = graph.compile()

if __name__ == "__main__":
    result = agent.invoke({
        'source': 'Kolkata',
        'destination': 'Goa',
        'need_hotel_stay': True,
        'journey_date': '2026-12-10',
        'trip_mode': 'SINGLE_WAY',
        'total_members': 2,
    })

    with open('FINAL_ITINERARY.md', 'w', encoding='utf-8') as f:
        f.write(result['final_suggestion'])
