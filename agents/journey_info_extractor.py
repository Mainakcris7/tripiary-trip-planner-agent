from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from typing import Optional

load_dotenv()


def get_trip_info_agent():
    '''
    Returns a LangChain chain for extracting trip information.

    The chain takes a `source` and `dest` as input and returns the best matching railway station codes and airport codes for both locations, following the specified rules and constraints.
    '''
    class Output(BaseModel):
        from_station_code: Optional[str]
        to_station_code: Optional[str]
        from_airport_code: Optional[str]
        to_airport_code: Optional[str]

    llm = ChatGoogleGenerativeAI(
        model='gemini-3.1-flash-lite',
        temperature=0.0
    ).with_structured_output(schema=Output)

    PROMPT = """
    You are a travel information assistant with expert knowledge of railways and airports worldwide.

    Given the SOURCE and DESTINATION of a trip, identify the single best option for each of the following:

    1. **from_station_code** – The most popular or well-connected railway station code near the SOURCE
    2. **to_station_code** – The most popular or well-connected railway station code near the DESTINATION
    3. **from_airport_code** – The nearest or most commonly used IATA airport code near the SOURCE
    4. **to_airport_code** – The nearest or most commonly used IATA airport code near the DESTINATION

    Rules:
    - DON'T hallucinate. If you truly cannot determine a code even after considering nearby alternatives, return NULL.

    - INTERNATIONAL TRIP RULE (VERY IMPORTANT):
      If the SOURCE country and DESTINATION country are different,
      then BOTH from_station_code and to_station_code MUST be NULL.

      Never return a railway station code for only one side of an international trip.
      Even if railway stations exist in those cities, railway station codes are NOT allowed for international trips.

    - If the SOURCE or DESTINATION city itself has no railway station or airport, find the NEAREST major one
    that a traveller would realistically use to begin or end their journey (within ~100–150 km if possible).

    - Prefer major/terminus stations over smaller ones when multiple exist in the same region.

    - Use official railway station codes (uppercase, 2–5 characters). For Indian cities, use Indian Railways codes.

    - Use standard IATA 3-letter airport codes.

    - Do NOT return NULL simply because the exact city lacks infrastructure — always check nearby alternatives first.

    Examples:

    SOURCE: Kolkata, India
    DESTINATION: Dhaka, Bangladesh

    from_station_code = NULL
    to_station_code = NULL
    from_airport_code = CCU
    to_airport_code = DAC
    - Both stations are NULL because it's an international trip, even though Kolkata and Dhaka have stations.

    SOURCE: Paris
    DESTINATION: Berlin

    from_station_code = NULL
    to_station_code = NULL
    from_airport_code = CDG
    to_airport_code = BER
    - Both stations are NULL because it's an international trip

    SOURCE: Kolkata
    DESTINATION: Delhi

    from_station_code = HWH
    to_station_code = NDLS
    from_airport_code = CCU
    to_airport_code = DEL
    - Airport and station codes for both cities, as it's a domestic trip
    """

    trip_prompt = ChatPromptTemplate.from_messages([
        ('system', PROMPT),
        ('user', 'Source: {source}, Destination: {dest}')
    ])

    chain = trip_prompt | llm

    return chain
