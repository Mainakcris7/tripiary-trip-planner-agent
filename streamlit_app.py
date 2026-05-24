import streamlit as st
from datetime import datetime, timedelta
import os
import time
from dotenv import load_dotenv

# Import agent components
from main import agent, AgentState

load_dotenv()

# Set page config
st.set_page_config(
    page_title="Trip Planner Agent",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

agent_config = {
    'run_name': 'trip_planner_agent_run',
    'tags': ['trip_planning_agent'],
    'metadata': {
        'description': 'An agent that plans a trip itinerary based on user input for source, destination, dates, and preferences. It gathers information about train and flight options, hotel stays, and destination research to create a comprehensive travel plan.'
    }
}

# Node display names for user-friendly output
NODE_DISPLAY_NAMES = {
    'get_trip_codes': '🌍 Extracting location codes...',
    'get_train_journey_options': '🚂 Searching for train options...',
    'get_flight_journey_options': '✈️ Searching for flight options...',
    'get_hotel_options': '🏨 Searching for hotel options...',
    'get_destination_research': '📚 Researching destination...',
    'get_train_trip_details': '📋 Analyzing train details...',
    'get_flight_trip_details': '📋 Analyzing flight details...',
    'get_hotel_details': '📋 Analyzing hotel details...',
    'get_final_itinerary': '✨ Generating final itinerary...',
}


def typewriter_effect(text, container, speed=0.01):
    """Display text with typewriter animation"""
    full_text = ""
    placeholder = container.empty()
    for char in text:
        full_text += char
        placeholder.markdown(full_text)
        time.sleep(speed)


# Initialize session state
if 'processing' not in st.session_state:
    st.session_state.processing = False

# Title
st.title("✈️ Trip Planner Agent")
st.markdown("### Plan your perfect trip with AI-powered recommendations!")

st.subheader("🎯 Trip Details")

source = st.text_input(
    "Source City",
    placeholder="e.g., Kolkata, Mumbai, Delhi, Bangalore"
)

destination = st.text_input(
    "Destination City",
    placeholder="e.g., Goa, Chennai, Jaipur, Kerala"
)

trip_mode = st.radio(
    "Trip Type",
    options=["SINGLE_WAY", "ROUND_TRIP"],
    index=0,
    horizontal=True
)

journey_date = st.date_input(
    "Journey Date",
    min_value=datetime.now(),
    help="Format: YYYY-MM-DD"
)

return_date = None
if trip_mode == "ROUND_TRIP":
    return_date = st.date_input(
        "Return Date",
        min_value=journey_date + timedelta(days=1),
        help="Format: YYYY-MM-DD (must be after journey date)"
    )

total_members = st.number_input(
    "Number of Travelers",
    min_value=1,
    max_value=10
)

need_hotel_stay = st.checkbox(
    "Need Hotel Accommodation?"
)

st.subheader("💭 Travel Preferences")
user_preferences = st.text_area(
    "Any specific preferences? (Budget, interests, dietary restrictions, etc.)",
    placeholder="e.g., Budget-friendly options, adventure activities, vegetarian food...",
    height=120
)

# ── Button / Spinner swap ──────────────────────────────────────────────────────
st.markdown("---")
col1, col2, col3 = st.columns([1, 1, 1])

with col2:
    btn_placeholder = st.empty()

    if st.session_state.processing:
        btn_placeholder.markdown(
            """
            <div style="
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                background-color: #FF4B4B;
                color: white;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 15px;
                font-weight: 600;
                width: 100%;
                height: 42px;
                box-sizing: border-box;
            ">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                     xmlns="http://www.w3.org/2000/svg"
                     style="animation: spin 0.9s linear infinite; flex-shrink: 0;">
                    <circle cx="12" cy="12" r="10" stroke="rgba(255,255,255,0.3)" stroke-width="3"/>
                    <path d="M12 2a10 10 0 0 1 10 10" stroke="white" stroke-width="3"
                          stroke-linecap="round"/>
                </svg>
                Planning your trip…
            </div>
            <style>
                @keyframes spin { to { transform: rotate(360deg); } }
            </style>
            """,
            unsafe_allow_html=True,
        )
        submit_button = False
    else:
        submit_button = btn_placeholder.button(
            "✨ Plan My Trip",
            use_container_width=True,
            type="primary",
        )

# Kick off processing on click
if submit_button and not st.session_state.processing:
    st.session_state.processing = True
    st.rerun()

# ── Main processing block ──────────────────────────────────────────────────────
if st.session_state.processing:
    if not source or not destination:
        st.error("❌ Please enter both source and destination cities!")
        st.session_state.processing = False
        st.rerun()
    else:
        trip_state = {
            'source': source,
            'destination': destination,
            'need_hotel_stay': need_hotel_stay,
            'journey_date': journey_date.strftime('%Y-%m-%d'),
            'return_date': return_date.strftime('%Y-%m-%d') if return_date else None,
            'trip_mode': trip_mode,
            'total_members': total_members,
            'user_preferences': user_preferences if user_preferences else None,
        }
        st.session_state.trip_details = trip_state

        st.markdown("---")
        node_placeholder = st.empty()

        try:
            final_result = None
            last_node = None

            for event in agent.stream(trip_state, config=agent_config):
                current_node = list(event.keys())[0] if event else None

                if current_node and current_node != last_node:
                    last_node = current_node
                    display_name = NODE_DISPLAY_NAMES.get(
                        current_node, f"Processing {current_node}...")
                    node_placeholder.info(display_name)

                if 'get_final_itinerary' in event:
                    final_result = event['get_final_itinerary'].get(
                        'final_suggestion')

        except Exception as e:
            node_placeholder.empty()
            st.session_state.processing = False
            st.error(f"❌ Error generating itinerary: {str(e)}")
            st.info("Please check your API keys and try again.")
            st.stop()

        # Store result, reset processing, then rerun so button reappears
        node_placeholder.empty()
        st.session_state.processing = False

        if final_result:
            st.session_state.itinerary_result = final_result
        else:
            st.session_state.itinerary_error = True

        # Rerun: processing=False means button renders, THEN results show below
        st.rerun()

# ── Results (shown after rerun, button is visible again) ──────────────────────
if st.session_state.get('itinerary_error'):
    del st.session_state['itinerary_error']
    st.error("❌ Failed to generate itinerary")

if 'itinerary_result' in st.session_state:
    st.success("✅ Itinerary generated successfully!")

    st.markdown("---")
    st.subheader("📋 Your Trip Itinerary")

    trip = st.session_state.trip_details
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("From", trip['source'])
    with col2:
        st.metric("To", trip['destination'])
    with col3:
        st.metric("Travelers", trip['total_members'])
    with col4:
        st.metric("Trip Type", trip['trip_mode'])

    st.markdown("---")
    st.subheader("✨ Your Personalized Itinerary")
    output_container = st.container(border=True)
    output_container.markdown(st.session_state.itinerary_result)

elif not st.session_state.processing:
    st.markdown("---")
    st.info("👈 Fill in your trip details and click 'Plan My Trip' to get started!")
