# Streamlit Trip Planner App

## Setup Instructions

### 1. Install Dependencies
Make sure all dependencies are installed:
```bash
uv sync
```

Or if using pip:
```bash
pip install -r requirements.txt
```

### 2. Environment Variables
Ensure your `.env` file has the following API keys:
```
SERPAPI_API_KEY=your_serpapi_key
GOOGLE_API_KEY=your_google_genai_key
TAVILY_API_KEY=your_tavily_key
```

### 3. Run the Streamlit App

```bash
streamlit run streamlit_app.py
```

Or with uv:
```bash
uv run streamlit run streamlit_app.py
```

The app will open at `http://localhost:8501`

## Features

- **Trip Details Tab**: Input source, destination, dates, and number of travelers
- **Preferences Tab**: Add custom travel preferences (budget, interests, etc.)
- **Real-time Processing**: Shows loading indicator while generating itinerary
- **Markdown Display**: Beautiful markdown rendering of the final itinerary
- **Download Option**: Save the itinerary as a markdown file

## Usage

1. Enter your source and destination cities
2. Select trip type (Single Way or Round Trip)
3. Choose travel dates and number of travelers
4. (Optional) Check if you need hotel accommodation
5. (Optional) Add your travel preferences
6. Click "Generate Itinerary" button
7. Wait for the AI to process and generate your personalized itinerary
8. Download the itinerary if needed

## Notes

- First run may take a minute as it gathers flights, trains, hotels, and destination research
- The app uses Gemini models for processing (3.5-flash for final itinerary)
- All outputs are displayed in markdown format with proper formatting
