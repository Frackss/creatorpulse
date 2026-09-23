import streamlit as st
import requests
import pandas as pd

from datetime import datetime, timedelta, timezone
from google import genai


# =========================================================
# PAGE SETUP
# =========================================================

st.set_page_config(
    page_title="CreatorPulse",
    page_icon="🍽️",
    layout="wide"
)

st.title("🍽️ CreatorPulse")
st.subheader("AI-powered creator discovery for the NYC dining scene")

st.write(
    "Discover emerging YouTube dining content, identify creators "
    "showing momentum, and use Gemini to interpret campaign opportunities."
)

st.caption(
    "NYU SPS × Google Hackathon prototype"
)


# =========================================================
# READ API KEYS FROM STREAMLIT SECRETS
# =========================================================

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]

# Keep the Gemini model in one place so it is easy to change later.
GEMINI_MODEL = st.secrets.get(
    "GEMINI_MODEL",
    "gemini-3.8-flash"
)


# =========================================================
# CONNECT TO GEMINI
# =========================================================

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# =========================================================
# YOUTUBE API HELPER
# =========================================================

def youtube_request(endpoint, params):

    params = params.copy()

    params["key"] = YOUTUBE_API_KEY

    url = f"https://www.googleapis.com/youtube/v3/{endpoint}"

    response = requests.get(
        url,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    return response.json()


# =========================================================
# FIND RECENT YOUTUBE VIDEOS
# =========================================================

@st.cache_data(ttl=600)
def find_recent_videos(
    search_term,
    days_back=14,
    max_results=12
):

    published_after = (
        datetime.now(timezone.utc)
        - timedelta(days=days_back)
    ).isoformat().replace(
        "+00:00",
        "Z"
    )

    # -----------------------------------------------------
    # 1. SEARCH FOR RECENT VIDEOS
    # -----------------------------------------------------

    search_data = youtube_request(
        "search",
        {
            "part": "snippet",
            "q": search_term,
            "type": "video",
            "order": "date",
            "publishedAfter": published_after,
            "maxResults": max_results,
            "regionCode": "US"
        }
    )

    video_ids = []

    for item in search_data.get(
        "items",
        []
    ):

        video_id = (
            item
            .get("id", {})
            .get("videoId")
        )

        if video_id:

            video_ids.append(
                video_id
            )

    if not video_ids:

        return pd.DataFrame()


    # -----------------------------------------------------
    # 2. GET VIDEO STATISTICS
    # -----------------------------------------------------

    video_data = youtube_request(
        "videos",
        {
            "part": "snippet,statistics",
            "id": ",".join(video_ids)
        }
    )


    # -----------------------------------------------------
    # 3. GET CREATOR / CHANNEL STATISTICS
    # -----------------------------------------------------

    channel_ids = list(
        {
            item["snippet"]["channelId"]
            for item in video_data.get(
                "items",
                []
            )
            if "snippet" in item
        }
    )

    channel_lookup = {}

    if channel_ids:

        channel_data = youtube_request(
            "channels",
            {
                "part": "snippet,statistics",
                "id": ",".join(
                    channel_ids
                )
            }
        )

        for channel in channel_data.get(
            "items",
            []
        ):

            channel_lookup[
                channel["id"]
            ] = channel


    # -----------------------------------------------------
    # 4. BUILD OUR DATASET
    # -----------------------------------------------------

    rows = []

    now = datetime.now(
        timezone.utc
    )

    for video in video_data.get(
        "items",
        []
    ):

        snippet = video.get(
            "snippet",
            {}
        )

        stats = video.get(
            "statistics",
            {}
        )

        published = pd.to_datetime(
            snippet.get(
                "publishedAt"
            ),
            utc=True
        ).to_pydatetime()

        hours_live = max(
            (
                now - published
            ).total_seconds()
            / 3600,
            1
        )

        views = int(
            stats.get(
                "viewCount",
                0
            )
        )

        likes = int(
            stats.get(
                "likeCount",
                0
            )
        )

        comments = int(
            stats.get(
                "commentCount",
                0
            )
        )

        channel_id = snippet.get(
            "channelId",
            ""
        )

        channel = channel_lookup.get(
            channel_id,
            {}
        )

        channel_stats = channel.get(
            "statistics",
            {}
        )

        subscribers = int(
            channel_stats.get(
                "subscriberCount",
                0
            )
        )

        # -------------------------------------------------
        # MOMENTUM CALCULATIONS
        # -------------------------------------------------

        views_per_hour = (
            views / hours_live
        )

        if subscribers > 0:

            views_per_subscriber = (
                views / subscribers
            )

        else:

            views_per_subscriber = None


        # -------------------------------------------------
        # THUMBNAIL
        # -------------------------------------------------

        thumbnails = snippet.get(
            "thumbnails",
            {}
        )

        thumbnail = ""

        if "high" in thumbnails:

            thumbnail = (
                thumbnails[
                    "high"
                ]["url"]
            )

        elif "medium" in thumbnails:

            thumbnail = (
                thumbnails[
                    "medium"
                ]["url"]
            )

        elif "default" in thumbnails:

            thumbnail = (
                thumbnails[
                    "default"
                ]["url"]
            )


        # -------------------------------------------------
        # STORE THE VIDEO
        # -------------------------------------------------

        rows.append(
            {
                "video_id":
                    video.get(
                        "id",
                        ""
                    ),

                "title":
                    snippet.get(
                        "title",
                        ""
                    ),

                "description":
                    snippet.get(
                        "description",
                        ""
                    ),

                "channel":
                    snippet.get(
                        "channelTitle",
                        ""
                    ),

                "channel_id":
                    channel_id,

                "published":
                    published,

                "views":
                    views,

                "likes":
                    likes,

                "comments":
                    comments,

                "subscribers":
                    subscribers,

                "views_per_hour":
                    views_per_hour,

                "views_per_subscriber":
                    views_per_subscriber,

                "thumbnail":
                    thumbnail
            }
        )


    df = pd.DataFrame(
        rows
    )

    if df.empty:

        return df


    # =====================================================
    # 5. CALCULATE THE MOMENTUM SCORE
    # =====================================================
    #
    # 70% = View Velocity
    # 30% = Performance Relative to Channel Size
    #
    # This is OUR prototype discovery signal.
    # It is NOT an official YouTube trending score.
    # =====================================================

    df[
        "velocity_score"
    ] = (
        df[
            "views_per_hour"
        ]
        .rank(
            pct=True
        )
        * 100
    )

    subscriber_score = (
        df[
            "views_per_subscriber"
        ]
        .rank(
            pct=True
        )
        * 100
    )

    subscriber_score = (
        subscriber_score
        .fillna(50)
    )

    df[
        "momentum_score"
    ] = (
        0.70
        * df[
            "velocity_score"
        ]
        +
        0.30
        * subscriber_score
    ).round(0)

    return (
        df
        .sort_values(
            "momentum_score",
            ascending=False
        )
        .reset_index(
            drop=True
        )
    )


# =========================================================
# CAMPAIGN SETUP
# =========================================================

st.divider()

st.header(
    "1. Campaign Setup"
)

col1, col2 = st.columns(
    2
)

with col1:

    brand = st.text_input(
        "Brand / Client",
        value="NYC Dining Collective"
    )

    campaign_goal = st.text_area(
        "Campaign Goal",
        value=(
            "Attract younger diners by connecting the brand "
            "with emerging NYC dining trends."
        )
    )

with col2:

    target_audience = st.text_input(
        "Target Audience",
        value=(
            "Gen Z and young adult diners "
            "in New York City"
        )
    )

    search_topic = st.text_input(
        "YouTube Topic",
        value=(
            "NYC hidden gem restaurants"
        )
    )


# =========================================================
# TREND DISCOVERY
# =========================================================

st.header(
    "2. Discover Emerging Content"
)

st.write(
    "CreatorPulse looks at recent public YouTube activity "
    "and ranks videos using a simple Momentum Score."
)

st.caption(
    "Momentum Score = 70% view velocity + 30% performance "
    "relative to channel size. "
    "It is not an official YouTube trending score."
)


if st.button(
    "🔎 Find NYC Dining Opportunities"
):

    try:

        with st.spinner(
            "Analyzing recent YouTube activity..."
        ):

            results = find_recent_videos(
                search_topic
            )

            st.session_state[
                "youtube_results"
            ] = results

    except requests.exceptions.HTTPError as e:

        st.error(
            "YouTube API request failed."
        )

        st.code(
            str(e)
        )

    except Exception as e:

        st.error(
            "Something went wrong while analyzing YouTube."
        )

        st.code(
            str(e)
        )


# =========================================================
# SHOW RESULTS
# =========================================================

if (
    "youtube_results"
    in st.session_state
):

    df = st.session_state[
        "youtube_results"
    ]

    if df.empty:

        st.warning(
            "No recent videos were found. "
            "Try a broader search topic."
        )

    else:

        st.success(
            f"Found {len(df)} recent videos."
        )


        # =================================================
        # TOP MOMENTUM VIDEOS
        # =================================================

        st.subheader(
            "🔥 Highest-Momentum Videos"
        )

        top_videos = (
            df.head(5)
        )

        for _, video in (
            top_videos.iterrows()
        ):

            st.divider()

            col1, col2 = (
                st.columns(
                    [1, 3]
                )
            )

            with col1:

                if video[
                    "thumbnail"
                ]:

                    st.image(
                        video[
                            "thumbnail"
                        ],
                        use_container_width=True
                    )

            with col2:

                st.write(
                    f"### {video['title']}"
                )

                st.write(
                    f"**Creator / Channel:** "
                    f"{video['channel']}"
                )

                metric1, metric2, metric3 = (
                    st.columns(3)
                )

                with metric1:

                    st.metric(
                        "Views",
                        f"{int(video['views']):,}"
                    )

                with metric2:

                    st.metric(
                        "Views / Hour",
                        f"{video['views_per_hour']:,.0f}"
                    )

                with metric3:

                    st.metric(
                        "Momentum Score",
                        f"{int(video['momentum_score'])}/100"
                    )

                video_url = (
                    "https://www.youtube.com/"
                    f"watch?v={video['video_id']}"
                )

                st.markdown(
                    f"[Open video on YouTube]({video_url})"
                )


        # =================================================
        # CREATOR SHORTLIST
        # =================================================

        st.divider()

        st.header(
            "3. Creator Shortlist"
        )

        st.write(
            "These creators are associated with the strongest "
            "recent momentum in the search results."
        )

        creators = (
            df
            .drop_duplicates(
                subset="channel_id"
            )
            .head(3)
        )

        creator_columns = (
            st.columns(3)
        )

        for (
            column,
            (_, creator)
        ) in zip(
            creator_columns,
            creators.iterrows()
        ):

            with column:

                if creator[
                    "thumbnail"
                ]:

                    st.image(
                        creator[
                            "thumbnail"
                        ],
                        use_container_width=True
                    )

                st.write(
                    f"### {creator['channel']}"
                )

                st.metric(
                    "Momentum",
                    f"{int(creator['momentum_score'])}/100"
                )

                st.write(
                    f"**Recent video:** "
                    f"{creator['title']}"
                )

                if (
                    creator[
                        "subscribers"
                    ]
                    > 0
                ):

                    st.write(
                        f"**Subscribers:** "
                        f"{int(creator['subscribers']):,}"
                    )

                else:

                    st.write(
                        "**Subscribers:** "
                        "Not publicly available"
                    )


        # =================================================
        # GEMINI TREND INTERPRETATION
        # =================================================

        st.divider()

        st.header(
            "4. Gemini Trend Interpretation"
        )

        st.write(
            "Gemini interprets the strongest YouTube signals "
            "and explains what they may mean for the campaign."
        )


        if st.button(
            "✨ Analyze Opportunity with Gemini"
        ):

            try:

                with st.spinner(
                    "Gemini is analyzing the opportunity..."
                ):

                    sample = (
                        df.head(8)[
                            [
                                "title",
                                "channel",
                                "views",
                                "views_per_hour",
                                "momentum_score"
                            ]
                        ]
                        .to_dict(
                            orient="records"
                        )
                    )

                    prompt = f"""
You are assisting a creator marketing strategist.

Brand:
{brand}

Campaign Goal:
{campaign_goal}

Target Audience:
{target_audience}

YouTube Search Topic:
{search_topic}

Recent YouTube results:
{sample}

Based ONLY on the supplied YouTube results:

1. Identify the clearest content pattern you observe.
2. Explain why that pattern could matter to this campaign.
3. Recommend two creator-content directions the brand could explore.
4. Identify one limitation or uncertainty in the available data.

Important rules:

- Do not call this an official YouTube trend.
- Do not invent audience demographics.
- Do not invent facts about the creators.
- Keep the response concise and useful for a marketing team.
"""

                    gemini_response = (
                        client.models.generate_content(
                            model=GEMINI_MODEL,
                            contents=prompt
                        )
                    )

                st.success(
                    "Gemini analysis complete!"
                )

                st.write(
                    gemini_response.text
                )

            except Exception as e:

                st.error(
                    "Gemini analysis failed."
                )

                st.code(
                    str(e)
                )


# =========================================================
# METHODOLOGY EXPLANATION
# =========================================================

st.divider()

with st.expander(
    "How does the Momentum Score work?"
):

    st.write(
        """
        **70% — View Velocity**

        Measures how quickly a video is gaining views based on
        how long it has been published.

        **30% — Performance Relative to Channel Size**

        Measures how large the video's view count is compared
        with the creator's public subscriber count.

        CreatorPulse uses this as a prototype campaign-discovery
        signal. It is not an official YouTube trending score.
        """
    )


# =========================================================
# CURRENT BUILD STATUS
# =========================================================

st.divider()

st.header(
    "Current Prototype Status"
)

st.write(
    """
    **Completed in this version:**

    - Campaign setup
    - YouTube trend discovery
    - Momentum Score
    - Top-video ranking
    - Creator shortlist
    - Gemini trend interpretation

    **Next build step:**

    Creator Fit Scoring — evaluate how well each shortlisted
    creator fits the specific campaign.
    """
)
)
