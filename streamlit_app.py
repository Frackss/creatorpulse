import streamlit as st
import requests
from google import genai


# ==========================================
# PAGE SETUP
# ==========================================

st.set_page_config(
    page_title="CreatorPulse",
    page_icon="🍽️",
    layout="wide"
)

st.title("🍽️ CreatorPulse")
st.subheader("AI-powered creator campaign accelerator")

st.write(
    "NYU SPS x Google Hackathon prototype"
)

st.info(
    "CreatorPulse helps restaurant marketing teams discover emerging "
    "YouTube dining trends and identify creators relevant to their campaigns."
)


# ==========================================
# READ API KEYS FROM STREAMLIT SECRETS
# ==========================================

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]


# ==========================================
# CONNECT TO GEMINI
# ==========================================

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# ==========================================
# GEMINI CONNECTION TEST
# ==========================================

st.header("1. Gemini Connection Test")

st.write(
    "First, test whether CreatorPulse can successfully connect to Gemini."
)

if st.button("Test Gemini"):

    try:

        with st.spinner("Asking Gemini..."):

            gemini_response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=(
                    "In one sentence, explain how creator marketing "
                    "can help a restaurant in New York City."
                )
            )

        st.success("Gemini connection works!")

        st.write(gemini_response.text)

    except Exception as e:

        st.error("Gemini test failed.")

        st.write(
            "Copy the error message below and check the API setup."
        )

        st.code(str(e))


# ==========================================
# YOUTUBE API CONNECTION TEST
# ==========================================

st.header("2. YouTube Data API Test")

st.write(
    "Search recent YouTube videos related to the New York dining scene."
)

search_term = st.text_input(
    "YouTube search topic",
    value="NYC hidden gem restaurants"
)


if st.button("Search YouTube"):

    try:

        with st.spinner("Searching recent YouTube videos..."):

            url = (
                "https://www.googleapis.com/youtube/v3/search"
            )

            params = {
                "part": "snippet",
                "q": search_term,
                "type": "video",
                "order": "date",
                "maxResults": 5,
                "key": YOUTUBE_API_KEY
            }

            yt_response = requests.get(
                url,
                params=params,
                timeout=30
            )

            yt_response.raise_for_status()

            youtube_data = yt_response.json()

        videos = youtube_data.get(
            "items",
            []
        )

        if len(videos) == 0:

            st.warning(
                "The YouTube connection worked, "
                "but no videos were found for this search."
            )

        else:

            st.success(
                "YouTube API connection works!"
            )

            st.write(
                f"Showing recent videos for: **{search_term}**"
            )

            for item in videos:

                snippet = item["snippet"]

                video_id = item["id"]["videoId"]

                title = snippet["title"]

                channel = snippet["channelTitle"]

                published = snippet["publishedAt"]

                description = snippet.get(
                    "description",
                    ""
                )

                thumbnails = snippet.get(
                    "thumbnails",
                    {}
                )

                thumbnail_url = None

                if "medium" in thumbnails:

                    thumbnail_url = (
                        thumbnails["medium"]["url"]
                    )

                elif "default" in thumbnails:

                    thumbnail_url = (
                        thumbnails["default"]["url"]
                    )

                st.divider()

                col1, col2 = st.columns(
                    [1, 3]
                )

                with col1:

                    if thumbnail_url:

                        st.image(
                            thumbnail_url
                        )

                with col2:

                    st.write(
                        f"### {title}"
                    )

                    st.write(
                        f"**Creator / Channel:** {channel}"
                    )

                    st.write(
                        f"**Published:** {published}"
                    )

                    if description:

                        st.write(
                            description[:250]
                        )

                    video_url = (
                        "https://www.youtube.com/"
                        f"watch?v={video_id}"
                    )

                    st.markdown(
                        f"[Open video on YouTube]({video_url})"
                    )

    except requests.exceptions.HTTPError:

        st.error(
            "YouTube API request failed."
        )

        st.write(
            "Google returned the following error:"
        )

        st.code(
            yt_response.text
        )

    except Exception as e:

        st.error(
            "Something went wrong while connecting to YouTube."
        )

        st.code(
            str(e)
        )


# ==========================================
# CURRENT PROTOTYPE STATUS
# ==========================================

st.divider()

st.header("CreatorPulse Prototype")

st.write(
    """
    This early prototype is testing the two Google technologies
    that will power CreatorPulse:
    
    **Gemini**
    
    Used for trend interpretation, creator-fit analysis,
    campaign brief generation, and first-pass content review.
    
    **YouTube Data API**
    
    Used to retrieve public YouTube videos and creator information
    relevant to emerging dining trends.
    """
)

st.caption(
    "Next step: transform YouTube results into an AI-assisted "
    "trend and creator discovery dashboard."
)
