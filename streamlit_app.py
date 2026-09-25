import streamlit as st
import requests
import pandas as pd
import json
import time
import base64
from pathlib import Path

from datetime import datetime, timedelta, timezone
from google import genai
from google.genai import types


# =========================================================
# PAGE SETUP
# =========================================================

st.set_page_config(
    page_title="CreatorPulse",
    page_icon="🍽️",
    layout="wide"
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=Rubik:ital,wght@0,300..900;1,300..900&family=Figtree:wght@400;500;600;700&display=swap');

    :root {
        --coral: #FF685F;
        --coral-dark: #E8524A;
        --ink: #2B2B2B;
        --cream: #F5F2EB;
        --white: #FFFFFF;
        --line: #E4DED2;
    }

    #MainMenu, footer, [data-testid="stDecoration"],
    .stAppDeployButton, [data-testid="stStatusWidget"] {
        display: none;
    }
    header[data-testid="stHeader"] { background: transparent; }
    .block-container { padding-top: 2.5rem; max-width: 1200px; }

    h1, h2, h3, h4, h5, h6 {
        font-family: 'Rubik', sans-serif;
        color: var(--ink);
        letter-spacing: -0.02em;
    }
    h2 { font-weight: 800; }

    .stButton > button, .stDownloadButton > button {
        background: var(--coral);
        color: var(--ink);
        border: 2px solid var(--ink);
        font-weight: 700;
        padding: 0.55rem 1.2rem;
        box-shadow: 3px 3px 0 var(--ink);
        transition: background-color 150ms ease, transform 150ms ease,
                    box-shadow 150ms ease;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        background: var(--coral-dark);
        color: var(--ink);
        border-color: var(--ink);
    }
    .stButton > button:active, .stDownloadButton > button:active {
        transform: translate(3px, 3px);
        box-shadow: none;
    }
    .stButton > button:focus-visible, .stDownloadButton > button:focus-visible {
        outline: 3px solid var(--ink);
        outline-offset: 3px;
    }

    [data-testid="stMetric"] {
        background: var(--white);
        border: 1px solid var(--line);
        border-radius: 10px;
        padding: 0.9rem 1rem;
    }
    [data-testid="stMetricValue"] {
        font-family: 'Bricolage Grotesque', sans-serif;
        font-weight: 800;
    }
    [data-testid="stExpander"] {
        background: var(--white);
        border-radius: 10px;
    }
    [data-testid="stImage"] img { border-radius: 10px; }
    hr { border-color: var(--line); }

    @media (prefers-reduced-motion: reduce) {
        .stButton > button, .stDownloadButton > button { transition: none; }
    }

    .cp-hero {
        border-bottom: 2px solid var(--ink);
        padding-bottom: 1.75rem;
    }
    .cp-badge {
        display: inline-block;
        background: var(--ink);
        color: var(--cream);
        border-radius: 999px;
        padding: 0.4rem 0.75rem;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .cp-brand {
        display: flex;
        align-items: center;
        gap: clamp(0.65rem, 2vw, 1.25rem);
        margin: 1.25rem 0;
    }
    .cp-logo {
        display: block;
        width: 638px;
        max-width: 100%;
        height: auto;
    }
    .cp-title {
        margin: 0;
        padding: 0;
        font-family: 'Rubik', sans-serif;
        font-weight: 800;
        font-size: clamp(2.8rem, 7vw, 5.2rem);
        line-height: 0.95;
        letter-spacing: -0.04em;
    }
    .cp-title .dot { color: var(--coral); }
    .cp-sub { font-size: 1.2rem; max-width: 60ch; opacity: 0.85; }
    </style>
    """,
    unsafe_allow_html=True,
)

logo_data = base64.b64encode(
    (Path(__file__).parent / "assets" / "creatorpulse-logo.svg").read_bytes()
).decode("ascii")

st.markdown(
    f"""
    <div class="cp-hero">
      <span class="cp-badge">NYU SPS × Google Hackathon</span>
      <div class="cp-brand">
        <h1 class="cp-title"><img class="cp-logo" src="data:image/svg+xml;base64,{logo_data}" alt="CreatorPulse" /></h1>
      </div>
      <p class="cp-sub">AI-powered creator discovery that turns emerging trends into campaign-ready creator matches.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


if "stage" not in st.session_state:
    st.session_state.stage = 1

STAGES = ["Discover", "Shortlist", "Create", "Approve"]

# Streamlit normally removes widget state when its stage is hidden.
# Re-saving these keys keeps campaign inputs and unfinished edits across stages.
PERSISTENT_WIDGET_KEYS = (
    "brand", "campaign_goal", "target_audience", "search_topic",
    "creator_choice", "brand_rules_input", "creator_draft_input",
    "final_decision_input", "reviewer_notes_input",
    "manual_review_status", "manual_review_notes", "manual_review_confirmed",
)
for widget_key in PERSISTENT_WIDGET_KEYS:
    if widget_key in st.session_state:
        st.session_state[widget_key] = st.session_state[widget_key]

# =========================================================
# READ API KEYS FROM STREAMLIT SECRETS
# =========================================================

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]

# Keep the Gemini model in one place so it is easy to change later.
GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite"
]


# =========================================================
# CONNECT TO GEMINI
# =========================================================

client = genai.Client(
    api_key=GEMINI_API_KEY
)

def generate_with_fallback(prompt):

    last_error = None

    for model_name in GEMINI_MODELS:

        # Try each model up to 2 times
        for attempt in range(2):

            try:

                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        thinking_config=types.ThinkingConfig(
                            thinking_level="low"
                        )
                    )
                )

                return response, model_name

            except Exception as e:

                last_error = e

                error_text = str(e)

                temporary_error = (
                    "503" in error_text
                    or "UNAVAILABLE" in error_text
                    or "high demand" in error_text.lower()
                )

                if temporary_error:

                    # Wait briefly before retrying
                    time.sleep(2)

                    continue

                # If it is not a temporary 503,
                # stop and show the real error.
                raise e

    raise last_error

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

@st.cache_data(ttl=3600)
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


DEMO_PATH = Path(__file__).parent / "demo" / "demo_campaign.json"
DEMO_KEYS = (
    "youtube_results", "trend_analysis", "creator_fit_results", "selected_creator",
    "generated_brief", "compliance_review", "brand", "campaign_goal",
    "target_audience", "search_topic", "brand_rules_input", "creator_draft_input",
)


def save_demo_snapshot():
    snapshot = {key: st.session_state[key] for key in DEMO_KEYS
                if key in st.session_state and key != "youtube_results"}
    df = st.session_state.get("youtube_results", pd.DataFrame())
    snapshot["youtube_results"] = json.loads(df.to_json(orient="records", date_format="iso"))
    snapshot["datetime_columns"] = [
        column for column in df.columns if pd.api.types.is_datetime64_any_dtype(df[column])
    ]
    snapshot["saved_at"] = datetime.now(timezone.utc).isoformat()
    snapshot["is_demo"] = True
    DEMO_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEMO_PATH.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    read_demo_snapshot.clear()
    return DEMO_PATH


@st.cache_data
def read_demo_snapshot(path, modified):
    # The modification timestamp invalidates cached reads after a new snapshot.
    snapshot = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(snapshot, dict) or snapshot.get("is_demo") is not True:
        raise ValueError("Invalid sample campaign")
    datetime.fromisoformat(snapshot["saved_at"])
    records = snapshot["youtube_results"]
    if not isinstance(records, list) or not records:
        raise ValueError("Sample campaign has no videos")
    df = pd.DataFrame(records)
    required = {"channel", "channel_id", "title", "description", "thumbnail", "views",
                "subscribers", "views_per_hour", "momentum_score", "video_id"}
    if not required.issubset(df.columns):
        raise ValueError("Sample campaign is missing video fields")
    columns = snapshot.get("datetime_columns", [])
    if not isinstance(columns, list):
        raise ValueError("Invalid datetime columns")
    for column in columns:
        df[column] = pd.to_datetime(df[column], utc=True)
    for key in DEMO_KEYS:
        if key not in snapshot or key == "youtube_results":
            continue
        value = snapshot[key]
        if key == "creator_fit_results":
            if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
                raise ValueError("Invalid creator fit results")
            fit_keys = {"channel", "title", "thumbnail", "overall_fit", "campaign_relevance",
                        "trend_alignment", "content_style_fit", "recent_performance", "brand_fit", "explanation", "risk"}
            if any(not fit_keys.issubset(item) for item in value):
                raise ValueError("Incomplete creator fit results")
        elif key == "selected_creator":
            if not isinstance(value, dict) or not (required - {"video_id"}).issubset(value):
                raise ValueError("Invalid selected creator")
        elif not isinstance(value, str):
            raise ValueError("Invalid sample text")
    snapshot["youtube_results"] = df
    return snapshot


def available_demo_snapshot():
    try:
        return read_demo_snapshot(str(DEMO_PATH), DEMO_PATH.stat().st_mtime_ns)
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return None


def load_demo_snapshot():
    snapshot = available_demo_snapshot()
    if snapshot is None:
        st.warning("Sample campaign isn't available yet.")
        return False
    # Never restore an old approval or leak the previous campaign into the sample.
    for key in (*DEMO_KEYS, "creator_draft", "final_decision", "reviewer_notes",
                *PERSISTENT_WIDGET_KEYS):
        st.session_state.pop(key, None)
    for key in DEMO_KEYS:
        if key in snapshot:
            st.session_state[key] = snapshot[key]
    selected = snapshot.get("selected_creator", {}).get("channel")
    options = [item["channel"] for item in snapshot.get("creator_fit_results", [])]
    if not options:
        options = snapshot["youtube_results"].drop_duplicates("channel_id").head(3)["channel"].tolist()
    if selected in options:
        st.session_state["creator_choice"] = selected
    st.session_state.demo_mode = True
    st.session_state.demo_saved_at = snapshot["saved_at"]
    return True


def use_saved_demo_result(key):
    if not st.session_state.get("demo_mode", False):
        return False
    snapshot = available_demo_snapshot()
    if snapshot is None or not snapshot.get(key):
        return False
    st.session_state[key] = snapshot[key]
    st.info("Gemini is unavailable, so this shows the saved sample result.")
    return True


def prepare_live_search():
    st.session_state.demo_mode = False
    # Do not label outputs from the old sample as results of a new live search.
    for key in ("youtube_results", "trend_analysis", "creator_fit_results", "selected_creator",
                "generated_brief", "compliance_review", "creator_draft", "final_decision",
                "reviewer_notes", "demo_saved_at", "creator_choice", "final_decision_input",
                "reviewer_notes_input", "manual_review_confirmed", "manual_review_notes"):
        st.session_state.pop(key, None)


def handle_youtube_error(error, message):
    if available_demo_snapshot() is not None:
        st.session_state["_load_demo_pending"] = True
        st.session_state["_youtube_fallback_error"] = str(error)
        st.rerun()
    st.error(message)
    with st.expander("Technical details"):
        st.code(str(error))


# Load before campaign widgets are instantiated, so their saved values can be restored.
if st.session_state.pop("_load_demo_pending", False):
    if load_demo_snapshot():
        st.session_state.stage = 1

# Stage navigation is gated by the existing workflow results.
def stage_ready(stage):
    if stage == 1:
        results = st.session_state.get("youtube_results")
        return results is not None and not results.empty
    if stage == 2:
        return bool(st.session_state.get("selected_creator"))
    if stage == 3:
        return bool(st.session_state.get("compliance_review"))
    return bool(st.session_state.get("final_decision"))


def go_to_stage(stage):
    st.session_state.stage = stage


def start_new_campaign():
    for key in (
        "youtube_results", "creator_fit_results", "selected_creator",
        "generated_brief", "creator_draft", "compliance_review",
        "final_decision", "reviewer_notes", "trend_analysis",
        "demo_mode", "demo_saved_at", "_youtube_fallback_error", "_load_demo_pending", "_saved_demo_json",
        *PERSISTENT_WIDGET_KEYS,
    ):
        st.session_state.pop(key, None)
    st.session_state.stage = 1


steps = []
for number, name in enumerate(STAGES, 1):
    current = number == st.session_state.stage
    completed = number < st.session_state.stage and stage_ready(number)
    css_class = "current" if current else "complete" if completed else "upcoming"
    marker = "✓" if completed else str(number)
    aria_current = ' aria-current="step"' if current else ""
    steps.append(f'<li class="cp-step {css_class}"{aria_current}>{marker} · {name}</li>')
st.markdown(
    """
    <style>
    ol.cp-steps { display:flex; flex-wrap:wrap; gap:0.75rem; padding:0;
        margin:1.5rem 0 2rem; list-style:none; }
    .cp-steps .cp-step { flex:1 1 130px; padding:0.85rem 1rem; border-radius:10px;
        font-weight:700; border:2px solid #E4DED2; }
    .cp-step.current { background:#FF685F; color:#2B2B2B; border-color:#2B2B2B; }
    .cp-step.complete { background:#2B2B2B; color:#F5F2EB; border-color:#2B2B2B; }
    .cp-step.upcoming { background:#FFFFFF; color:#2B2B2B; opacity:0.6; }
    .cp-decision { padding:1.25rem; border-radius:10px; font-size:1.5rem;
        font-weight:800; border:3px solid #FF685F; background:#FFFFFF; color:#2B2B2B; }
    .cp-decision.revise { border-color:#D99A00; background:#FFF4D6; }
    </style>
    <ol class="cp-steps" aria-label="Campaign progress">""" + "".join(steps) + "</ol>",
    unsafe_allow_html=True,
)

if st.session_state.get("demo_mode", False):
    saved_date = datetime.fromisoformat(st.session_state.demo_saved_at).strftime("%b %d")
    st.markdown(
        f'<span style="display:inline-block;padding:0.35rem 0.75rem;border-radius:999px;'
        f'background:#F5F2EB;border:1px solid #E4DED2;color:#2B2B2B;font-size:0.8rem;">'
        f'Sample campaign · saved {saved_date}</span>', unsafe_allow_html=True,
    )

brand = st.session_state.get("brand", "NYC Dining Collective")
campaign_goal = st.session_state.get("campaign_goal", "")
target_audience = st.session_state.get("target_audience", "")
search_topic = st.session_state.get("search_topic", "")
df = st.session_state.get("youtube_results")

if st.session_state.stage == 1:
    # =========================================================
    # CAMPAIGN SETUP
    # =========================================================


    st.header(
        "Campaign Setup"
    )

    col1, col2 = st.columns(
        2
    )

    with col1:

        brand = st.text_input(
            "Brand / Client",
            value=None if "brand" in st.session_state else ("NYC Dining Collective"),
            key="brand",
        )

        campaign_goal = st.text_area(
            "Campaign Goal",
            value=(
                None if "campaign_goal" in st.session_state else ("Attract younger diners by connecting the brand "
                "with emerging NYC dining trends.")
            ),
            key="campaign_goal",
        )

    with col2:

        target_audience = st.text_input(
            "Target Audience",
            value=(
                None if "target_audience" in st.session_state else ("Gen Z and young adult diners "
                "in New York City")
            ),
            key="target_audience",
        )

        search_topic = st.text_input(
            "YouTube Topic",
            value=(
                None if "search_topic" in st.session_state else ("NYC hidden gem restaurants")
            ),
            key="search_topic",
        )


    # =========================================================
    # TREND DISCOVERY
    # =========================================================

    st.header(
        "Discover Emerging Content"
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


    live_column, sample_column = st.columns(2)
    with live_column:
        find_clicked = st.button("🔎 Find Creator Opportunities", on_click=prepare_live_search)
    with sample_column:
        st.markdown(
            '<style>.st-key-load_sample button, .st-key-load_sample button:hover {background:#FFFFFF;color:#2B2B2B;'
            'border:2px solid #2B2B2B;}</style>', unsafe_allow_html=True,
        )
        if st.button("▶ Load sample campaign", key="load_sample", type="secondary"):
            st.session_state["_load_demo_pending"] = True
            st.rerun()

    if "_youtube_fallback_error" in st.session_state:
        st.info("Live YouTube data is unavailable right now, so we loaded a saved sample campaign.")
        with st.expander("Technical details"):
            st.code(st.session_state.pop("_youtube_fallback_error"))

    if find_clicked:
        st.session_state.demo_mode = False
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

            handle_youtube_error(e, "YouTube API request failed.")

        except Exception as e:

            handle_youtube_error(e, "Something went wrong while analyzing YouTube.")


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


            # =========================================================
            # METHODOLOGY EXPLANATION
            # =========================================================

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


            # =================================================
            # GEMINI TREND INTERPRETATION
            # =================================================

            st.header(
                "Gemini Trend Interpretation"
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

                    gemini_response, model_used = generate_with_fallback(
                        prompt
                    )


                    st.success(
                        "Gemini analysis complete!"
                    )

                    st.session_state["trend_analysis"] = gemini_response.text

                except Exception as e:

                    if not use_saved_demo_result("trend_analysis"):
                        st.error("Gemini analysis failed.")

                    with st.expander("Technical details"):
                        st.code(str(e))



            if "trend_analysis" in st.session_state:
                st.write(st.session_state["trend_analysis"])

if st.session_state.stage == 2:
    # =================================================
    # CREATOR SHORTLIST
    # =================================================


    st.header(
        "Creator Shortlist"
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
    # CREATOR FIT SCORING
    # =================================================


    st.header(
        "Creator Fit Scoring"
    )

    st.write(
        "Gemini evaluates each shortlisted creator against "
        "the campaign using five transparent criteria."
    )

    st.caption(
        "Gemini scores the individual criteria. "
        "CreatorPulse calculates the final weighted score."
    )

    with st.expander(
        "How is Creator Fit calculated?"
    ):

        st.write(
            """
                **30% — Campaign Relevance**

                How closely the creator's observed content relates
                to the campaign and brand.

                **25% — Trend Alignment**

                How closely the creator's recent content connects
                with the dining topic being analyzed.

                **20% — Content Style Fit**

                How compatible the observed content style appears
                with the campaign.

                **15% — Recent Performance**

                Uses the supplied YouTube performance signals,
                including momentum and view velocity.

                **10% — Brand Fit**

                Whether the supplied content appears appropriate
                for the campaign based only on the available evidence.
                """
        )


    if st.button(
        "✨ Score Creator Fit"
    ):

        try:

            creator_fit_results = []

            progress = st.progress(0)

            creator_list = list(
                creators.iterrows()
            )

            for position, (_, creator) in enumerate(
                creator_list
            ):

                with st.spinner(
                    f"Analyzing {creator['channel']}..."
                ):

                    prompt = f"""
You are assisting a creator marketing strategist.

Evaluate the creator ONLY using the supplied evidence.

CAMPAIGN

Brand:
{brand}

Campaign Goal:
{campaign_goal}

Target Audience:
{target_audience}

YouTube Topic:
{search_topic}


CREATOR EVIDENCE

Creator / Channel:
{creator['channel']}

Recent Video Title:
{creator['title']}

Recent Video Description:
{creator['description']}

Video Views:
{int(creator['views'])}

Public Subscriber Count:
{int(creator['subscribers'])}

Views Per Hour:
{creator['views_per_hour']:.2f}

Momentum Score:
{int(creator['momentum_score'])}/100


Score the creator from 0 to 100 on exactly these five dimensions:

1. campaign_relevance
How closely the observed content relates to the campaign.

2. trend_alignment
How closely the observed content aligns with the YouTube topic being analyzed.

3. content_style_fit
How compatible the observed content appears with the campaign's intended direction.

4. recent_performance
Evaluate only from the supplied performance information.

5. brand_fit
Evaluate suitability for this campaign only from the supplied evidence.

Also provide:

explanation:
A concise explanation of why the creator may or may not fit.

risk:
One limitation, concern, or uncertainty the marketer should know.

IMPORTANT RULES:

Do not infer age, gender, income, ethnicity, location, or other audience demographics.

Do not invent the creator's history.

Do not claim to know their full audience.

Do not invent performance data.

Use only the information supplied.

Return ONLY valid JSON using exactly this format:

{{
    "campaign_relevance": 0,
    "trend_alignment": 0,
    "content_style_fit": 0,
    "recent_performance": 0,
    "brand_fit": 0,
    "explanation": "",
    "risk": ""
}}
"""

                    gemini_response, model_used = generate_with_fallback(
                        prompt
                    )

                    st.caption(
                        f"AI analysis completed using {model_used}"
                    )

                    raw_text = (
                        gemini_response.text.strip()
                    )

                    # Remove markdown code fences if Gemini adds them
                    raw_text = raw_text.replace(
                        "```json",
                        ""
                    )

                    raw_text = raw_text.replace(
                        "```",
                        ""
                    ).strip()

                    # Find only the JSON object
                    start = raw_text.find("{")
                    end = raw_text.rfind("}")

                    if start == -1 or end == -1:

                        raise ValueError(
                            "Gemini did not return valid JSON."
                        )

                    result = json.loads(
                        raw_text[
                            start:end + 1
                        ]
                    )

                    # ---------------------------------
                    # KEEP SCORES BETWEEN 0 AND 100
                    # ---------------------------------

                    campaign_relevance = max(
                        0,
                        min(
                            100,
                            float(
                                result[
                                    "campaign_relevance"
                                ]
                            )
                        )
                    )

                    trend_alignment = max(
                        0,
                        min(
                            100,
                            float(
                                result[
                                    "trend_alignment"
                                ]
                            )
                        )
                    )

                    content_style_fit = max(
                        0,
                        min(
                            100,
                            float(
                                result[
                                    "content_style_fit"
                                ]
                            )
                        )
                    )

                    recent_performance = max(
                        0,
                        min(
                            100,
                            float(
                                result[
                                    "recent_performance"
                                ]
                            )
                        )
                    )

                    brand_fit = max(
                        0,
                        min(
                            100,
                            float(
                                result[
                                    "brand_fit"
                                ]
                            )
                        )
                    )


                    # ---------------------------------
                    # PYTHON CALCULATES FINAL SCORE
                    # ---------------------------------

                    overall_fit = round(
                        campaign_relevance * 0.30
                        +
                        trend_alignment * 0.25
                        +
                        content_style_fit * 0.20
                        +
                        recent_performance * 0.15
                        +
                        brand_fit * 0.10
                    )


                    creator_fit_results.append(
                        {
                            "channel":
                                creator[
                                    "channel"
                                ],

                            "title":
                                creator[
                                    "title"
                                ],

                            "thumbnail":
                                creator[
                                    "thumbnail"
                                ],

                            "campaign_relevance":
                                round(
                                    campaign_relevance
                                ),

                            "trend_alignment":
                                round(
                                    trend_alignment
                                ),

                            "content_style_fit":
                                round(
                                    content_style_fit
                                ),

                            "recent_performance":
                                round(
                                    recent_performance
                                ),

                            "brand_fit":
                                round(
                                    brand_fit
                                ),

                            "overall_fit":
                                overall_fit,

                            "explanation":
                                result.get(
                                    "explanation",
                                    ""
                                ),

                            "risk":
                                result.get(
                                    "risk",
                                    ""
                                )
                        }
                    )

                progress.progress(
                    (
                        position + 1
                    )
                    /
                    len(
                        creator_list
                    )
                )


            creator_fit_results = sorted(
                creator_fit_results,
                key=lambda x: x[
                    "overall_fit"
                ],
                reverse=True
            )

            st.session_state[
                "creator_fit_results"
            ] = creator_fit_results

            st.success(
                "Creator Fit analysis complete!"
            )

        except Exception as e:

            if not use_saved_demo_result("creator_fit_results"):
                st.error("Creator Fit scoring failed.")

            with st.expander("Technical details"):
                st.code(str(e))


    # =================================================
    # DISPLAY CREATOR FIT RESULTS
    # =================================================

    if (
        "creator_fit_results"
        in st.session_state
    ):

        fit_results = (
            st.session_state[
                "creator_fit_results"
            ]
        )

        st.subheader(
            "Creator Fit Results"
        )

        st.caption(
            "Higher scores indicate stronger alignment "
            "with this specific campaign based on the "
            "limited evidence supplied."
        )

        for rank, result in enumerate(
            fit_results,
            start=1
        ):

            st.divider()

            col1, col2 = (
                st.columns(
                    [1, 3]
                )
            )

            with col1:

                if result[
                    "thumbnail"
                ]:

                    st.image(
                        result[
                            "thumbnail"
                        ],
                        use_container_width=True
                    )

            with col2:

                st.write(
                    f"### #{rank} — "
                    f"{result['channel']}"
                )

                st.metric(
                    "Overall Campaign Fit",
                    f"{result['overall_fit']}/100"
                )

                score_col1, score_col2 = (
                    st.columns(2)
                )

                with score_col1:

                    st.write(
                        "**Campaign Relevance:** "
                        f"{result['campaign_relevance']}/100"
                    )

                    st.write(
                        "**Trend Alignment:** "
                        f"{result['trend_alignment']}/100"
                    )

                    st.write(
                        "**Content Style Fit:** "
                        f"{result['content_style_fit']}/100"
                    )

                with score_col2:

                    st.write(
                        "**Recent Performance:** "
                        f"{result['recent_performance']}/100"
                    )

                    st.write(
                        "**Brand Fit:** "
                        f"{result['brand_fit']}/100"
                    )

                st.write(
                    "**Why this creator may fit:**"
                )

                st.write(
                    result[
                        "explanation"
                    ]
                )

                st.write(
                    "**Limitation / Watchout:**"
                )

                st.write(
                    result[
                        "risk"
                    ]
                )


            # =================================================
    # HUMAN CREATOR SELECTION
    # =================================================


    st.header(
        "Human Creator Selection"
    )

    st.write(
        "CreatorPulse provides recommendations, but the marketer "
        "makes the final creator decision."
    )


    # -------------------------------------------------
    # BUILD CREATOR OPTIONS
    # -------------------------------------------------

    creator_options = []

    fit_lookup = {}


    # If Creator Fit worked, use the ranked results
    if (
        "creator_fit_results"
        in st.session_state
        and st.session_state[
            "creator_fit_results"
        ]
    ):

        fit_results = st.session_state[
            "creator_fit_results"
        ]

        for result in fit_results:

            creator_options.append(
                result["channel"]
            )

            fit_lookup[
                result["channel"]
            ] = result


    # If Creator Fit failed, fall back to the shortlist
    else:

        creator_options = (
            creators[
                "channel"
            ]
            .tolist()
        )


    # Remove duplicates while keeping order
    creator_options = list(
        dict.fromkeys(
            creator_options
        )
    )


    # -------------------------------------------------
    # CREATOR DROPDOWN
    # -------------------------------------------------

    if creator_options:

        selected_creator_name = st.selectbox(
            "Choose the creator you want to continue with:",
            creator_options,
            key="creator_choice",
        )


        # ---------------------------------------------
        # FIND FULL CREATOR DATA
        # ---------------------------------------------

        selected_rows = (
            creators[
                creators[
                    "channel"
                ]
                ==
                selected_creator_name
            ]
        )

        if not selected_rows.empty:

            selected_creator = (
                selected_rows.iloc[0]
            )

            # Save creator information for later steps
            st.session_state[
                "selected_creator"
            ] = {
                "channel":
                    selected_creator[
                        "channel"
                    ],

                "channel_id":
                    selected_creator[
                        "channel_id"
                    ],

                "title":
                    selected_creator[
                        "title"
                    ],

                "description":
                    selected_creator[
                        "description"
                    ],

                "views":
                    int(
                        selected_creator[
                            "views"
                        ]
                    ),

                "subscribers":
                    int(
                        selected_creator[
                            "subscribers"
                        ]
                    ),

                "views_per_hour":
                    float(
                        selected_creator[
                            "views_per_hour"
                        ]
                    ),

                "momentum_score":
                    int(
                        selected_creator[
                            "momentum_score"
                        ]
                    ),

                "thumbnail":
                    selected_creator[
                        "thumbnail"
                    ]
            }


            # -----------------------------------------
            # DISPLAY SELECTED CREATOR
            # -----------------------------------------

            st.success(
                f"Selected Creator: "
                f"{selected_creator_name}"
            )

            col1, col2 = st.columns(
                [1, 3]
            )

            with col1:

                if selected_creator[
                    "thumbnail"
                ]:

                    st.image(
                        selected_creator[
                            "thumbnail"
                        ],
                        use_container_width=True
                    )


            with col2:

                st.write(
                    f"### {selected_creator_name}"
                )

                st.write(
                    f"**Recent Video:** "
                    f"{selected_creator['title']}"
                )

                st.write(
                    f"**Momentum Score:** "
                    f"{int(selected_creator['momentum_score'])}/100"
                )


                if (
                    selected_creator_name
                    in fit_lookup
                ):

                    selected_fit = (
                        fit_lookup[
                            selected_creator_name
                        ]
                    )

                    st.write(
                        f"**Campaign Fit:** "
                        f"{selected_fit['overall_fit']}/100"
                    )


                if (
                    int(
                        selected_creator[
                            "subscribers"
                        ]
                    )
                    > 0
                ):

                    st.write(
                        f"**Subscribers:** "
                        f"{int(selected_creator['subscribers']):,}"
                    )

                else:

                    st.write(
                        "**Subscribers:** "
                        "Not publicly available"
                    )


            st.info(
                "AI provides recommendations. "
                "The marketer makes the final creator selection."
            )

    else:

        st.warning(
            "No creators are available yet. "
            "Run the YouTube discovery step first."
        )


if st.session_state.stage == 3:
            # =================================================
    # PERSONALIZED CREATOR BRIEF
    # =================================================


    st.header(
        "Personalized Creator Brief"
    )

    st.write(
        "Gemini turns the campaign, trend, and selected creator "
        "into a creator-specific campaign brief."
    )

    st.caption(
        "The brief uses only the campaign information and "
        "observed creator content available in CreatorPulse."
    )


    # -------------------------------------------------
    # CHECK THAT A CREATOR HAS BEEN SELECTED
    # -------------------------------------------------

    if (
        "selected_creator"
        in st.session_state
    ):

        selected_creator = (
            st.session_state[
                "selected_creator"
            ]
        )

        st.write(
            f"**Selected Creator:** "
            f"{selected_creator['channel']}"
        )


        if st.button(
            "✨ Generate Personalized Brief"
        ):

            try:

                with st.spinner(
                    "Gemini is creating the campaign brief..."
                ):

                    brief_prompt = f"""
You are assisting a creator marketing strategist.

Create a concise creator-specific campaign brief using ONLY
the information supplied below.


CAMPAIGN

Brand:
{brand}

Campaign Goal:
{campaign_goal}

Target Audience:
{target_audience}

YouTube Topic / Emerging Content Area:
{search_topic}


SELECTED CREATOR

Creator / Channel:
{selected_creator['channel']}

Recent Video:
{selected_creator['title']}

Recent Video Description:
{selected_creator['description']}

Recent Video Views:
{selected_creator['views']}

Public Subscriber Count:
{selected_creator['subscribers']}

Momentum Score:
{selected_creator['momentum_score']}/100


Create the brief using exactly these sections:

## Campaign Concept

Give the campaign idea a short, memorable title.

## Why This Creator Fits

Explain why the observed creator content could fit this campaign.

## Opening Hook

Suggest one possible opening hook for the creator's video.

## Creative Direction

Describe the overall approach for the content.

## Key Talking Points

Provide 3 to 5 concise talking points.

## Required Campaign Elements

List the elements the brand should require.

## Things to Avoid

List 2 to 4 things the creator should avoid.

## Call to Action

Provide one suggested call to action.


IMPORTANT RULES:

- Use only the supplied evidence.
- Do not invent facts about the creator.
- Do not claim to know their audience demographics.
- Do not impersonate the creator.
- Do not say the creator personally likes the brand unless that information was supplied.
- Preserve creator flexibility instead of writing a complete script.
- Keep the brief concise and presentation-ready.
"""

                    brief_response, brief_model_used = (
                        generate_with_fallback(
                            brief_prompt
                        )
                    )

                    generated_brief = (
                        brief_response.text
                    )

                    # Save the brief for later steps
                    st.session_state[
                        "generated_brief"
                    ] = generated_brief


                st.success(
                    "Personalized brief created!"
                )

                st.caption(
                    f"Generated using "
                    f"{brief_model_used}"
                )

            except Exception as e:

                if not use_saved_demo_result("generated_brief"):
                    st.error("Brief generation failed.")

                with st.expander("Technical details"):
                    st.code(str(e))


        # -------------------------------------------------
        # DISPLAY SAVED BRIEF
        # -------------------------------------------------

        if (
            "generated_brief"
            in st.session_state
        ):

            st.subheader(
                "Campaign Brief"
            )

            st.markdown(
                st.session_state[
                    "generated_brief"
                ]
            )

            st.info(
                "This is an AI-generated first draft. "
                "The marketing team can revise it before "
                "sending it to the creator."
            )


    else:

        st.warning(
            "Choose a creator above before generating a brief."
        )

            # =================================================
    # BRAND / COMPLIANCE REVIEW
    # =================================================


    st.header(
        "Brand & Content Review"
    )

    st.write(
        "CreatorPulse performs a first-pass review of a creator draft "
        "against the brand guidelines supplied by the marketing team."
    )

    st.caption(
        "Gemini only checks against the rules provided below. "
        "A human reviewer makes the final approval decision."
    )


    # -------------------------------------------------
    # BRAND GUIDELINES
    # -------------------------------------------------

    brand_rules = st.text_area(
        "Brand Guidelines",
        value=None if "brand_rules_input" in st.session_state else ("""1. Sponsored content must clearly disclose #ad.
2. Do not say the restaurant or brand is "the best in NYC."
3. Do not make unsupported health or nutrition claims.
4. Do not negatively attack competing restaurants.
5. Do not guarantee that every customer will have the same experience."""),
        height=180,
        key="brand_rules_input",
    )


    # -------------------------------------------------
    # CREATOR DRAFT
    # -------------------------------------------------

    creator_draft = st.text_area(
        "Creator Draft",
        value=None if "creator_draft_input" in st.session_state else ("""I found the best restaurant in all of NYC and everyone is guaranteed to love it.

NYC Dining Collective sent me here to check out this hidden gem. The food is incredible and you absolutely need to try it."""),
        height=180,
        key="creator_draft_input",
    )


    # -------------------------------------------------
    # REVIEW BUTTON
    # -------------------------------------------------

    if st.button(
        "🔍 Review Creator Draft"
    ):

        try:

            with st.spinner(
                "Gemini is reviewing the draft..."
            ):

                review_prompt = f"""
You are performing a first-pass brand guideline review
for a creator marketing campaign.

Evaluate the creator draft ONLY against the supplied
brand guidelines.

BRAND

{brand}


BRAND GUIDELINES

{brand_rules}


CREATOR DRAFT

{creator_draft}


Return your review using exactly these sections:

## Status

Choose only one:

PASS
REVISE
BLOCK


## Summary

Give a short explanation of the overall result.


## Issues Found

For every issue, provide:

- Draft Excerpt
- Brand Rule
- Why It Conflicts
- Suggested Revision

If there are no issues, write:
"No conflicts identified against the supplied guidelines."


## Human Review Note

Briefly explain what still requires human judgment.


IMPORTANT RULES:

- Evaluate ONLY against the supplied brand guidelines.
- Do not invent additional brand rules.
- Do not invent laws or legal requirements.
- Do not make the final approval decision.
- Do not rewrite the entire creator script unless necessary.
- Keep suggested changes concise.
"""

                review_response, review_model_used = (
                    generate_with_fallback(
                        review_prompt
                    )
                )

                review_text = (
                    review_response.text
                )

                # Save result for Step 15
                st.session_state[
                    "compliance_review"
                ] = review_text

                st.session_state[
                    "creator_draft"
                ] = creator_draft


            st.success(
                "First-pass review complete!"
            )

            st.caption(
                f"Reviewed using "
                f"{review_model_used}"
            )

        except Exception as e:

            if not use_saved_demo_result("compliance_review"):
                st.error("Content review failed.")

            with st.expander("Technical details"):
                st.code(str(e))


    with st.expander("Manual review — continue without Gemini"):
        st.write(
            "If Gemini is unavailable or its quota is exhausted, review the "
            "creator draft against the brand guidelines yourself. This records "
            "a human review, not an AI review or final launch approval."
        )
        manual_status = st.radio(
            "Manual review result", ["REVISE", "PASS", "BLOCK"],
            key="manual_review_status",
        )
        manual_notes = st.text_area(
            "Manual review notes",
            placeholder="Record any issues, required revisions, or why the draft passes.",
            key="manual_review_notes",
        )
        manual_confirmed = st.checkbox(
            "I reviewed the current creator draft against the brand guidelines.",
            key="manual_review_confirmed",
        )
        manual_ready = (
            manual_confirmed and bool(manual_notes.strip())
            and bool(creator_draft.strip()) and bool(brand_rules.strip())
        )
        if st.button("Save manual review", disabled=not manual_ready):
            st.session_state["compliance_review"] = (
                "## Review method\n\nManual human review — no AI review was performed.\n\n"
                f"## Status\n\n{manual_status}\n\n"
                f"## Summary\n\n{manual_notes.strip()}\n\n"
                "## Human Review Note\n\n"
                "A human reviewed the creator draft against the supplied brand guidelines. "
                "Final campaign approval remains a separate decision."
            )
            st.session_state["creator_draft"] = creator_draft
            # A new review must receive a fresh final approval.
            for decision_key in ("final_decision", "reviewer_notes", "final_decision_input", "reviewer_notes_input"):
                st.session_state.pop(decision_key, None)
            st.success("Manual review saved. You can continue to Approve.")
        if not manual_ready:
            st.caption(
                "Provide a draft and brand guidelines, add review notes, and "
                "confirm you reviewed them to save a manual review."
            )


    # -------------------------------------------------
    # DISPLAY SAVED REVIEW
    # -------------------------------------------------

    if (
        "compliance_review"
        in st.session_state
    ):

        st.subheader(
            "Review Results"
        )

        st.markdown(
            st.session_state[
                "compliance_review"
            ]
        )

        st.info(
            "This review is decision support only. "
            "The marketing team retains final approval."
        )


if st.session_state.stage == 4:
            # =================================================
    # FINAL HUMAN APPROVAL
    # =================================================


    st.header(
        "Final Human Approval"
    )

    st.write(
        "Gemini provides decision support, but the marketing team "
        "makes the final campaign approval decision."
    )


    # Only show approval controls after a review exists
    if (
        "compliance_review"
        in st.session_state
    ):

        final_decision = st.radio(
            "Final Campaign Decision",
            [
                "Needs Revision",
                "Approved for Launch"
            ],
            index=None if "final_decision_input" in st.session_state else (0),
            key="final_decision_input",
        )


        reviewer_notes = st.text_area(
            "Reviewer Notes (optional)",
            placeholder=(
                "Add any comments, required changes, "
                "or approval notes here."
            ),
            height=120,
            key="reviewer_notes_input",
        )


        if st.button(
            "Confirm Final Decision"
        ):

            st.session_state[
                "final_decision"
            ] = final_decision

            st.session_state[
                "reviewer_notes"
            ] = reviewer_notes


            if (
                final_decision
                ==
                "Approved for Launch"
            ):

                st.success(
                    "✅ Campaign approved for launch."
                )

            else:

                st.warning(
                    "⚠️ Campaign requires revision before launch."
                )


    else:

        st.info(
            "Run the Brand & Content Review above "
            "before making a final decision."
        )


    # -------------------------------------------------
    # DISPLAY SAVED FINAL DECISION
    # -------------------------------------------------

    if (
        "final_decision"
        in st.session_state
    ):

        st.subheader(
            "Final Decision"
        )

        decision = (
            st.session_state[
                "final_decision"
            ]
        )

        if (
            decision
            ==
            "Approved for Launch"
        ):

            st.success(
                "✅ Approved for Launch"
            )

        else:

            st.warning(
                "⚠️ Needs Revision"
            )


        if (
            st.session_state.get(
                "reviewer_notes"
            )
        ):

            st.write(
                "**Reviewer Notes:**"
            )

            st.write(
                st.session_state[
                    "reviewer_notes"
                ]
            )


        st.caption(
            "Final approval is made by the human marketing team, "
            "not by the AI system."
        )



    st.header("Campaign summary")
    data_source = "saved sample campaign" if st.session_state.get("demo_mode") else "live YouTube data"
    st.write(f"Data source: {data_source}")
    summary_creator = st.session_state.get("selected_creator", {})
    summary_fit = next(
        (item for item in st.session_state.get("creator_fit_results", [])
         if item["channel"] == summary_creator.get("channel")),
        {},
    )
    fit_score = f"{summary_fit['overall_fit']}/100" if summary_fit else "—"
    st.write(f"**Brand:** {brand}")
    st.write(f"**Target audience:** {target_audience}")
    st.write(f"**YouTube topic:** {search_topic}")
    if summary_creator.get("thumbnail"):
        st.image(summary_creator["thumbnail"], width=160)
    st.write(f"**Selected creator:** {summary_creator.get('channel', '—')}")
    st.metric("Overall fit score", fit_score)
    with st.expander("Generated brief"):
        st.markdown(st.session_state.get("generated_brief", "Not started"))
    st.subheader("Review result summary")
    st.markdown(st.session_state.get("compliance_review", "—"))
    saved_decision = st.session_state.get("final_decision")
    if saved_decision:
        approved = saved_decision == "Approved for Launch"
        banner_class = "cp-decision" if approved else "cp-decision revise"
        banner_text = "✅ Approved for Launch" if approved else "⚠️ Needs Revision"
        st.markdown(
            f'<div class="{banner_class}" role="status">{banner_text}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("Confirm your final decision above to complete the campaign.")
    st.write("**Reviewer notes:**")
    st.write(st.session_state.get("reviewer_notes") or "—")

    campaign_markdown = (
        "# CreatorPulse campaign summary\n\n"
        f"Data source: {data_source}\n\n"
        f"**Brand:** {brand}\n\n"
        f"**Campaign goal:** {campaign_goal}\n\n"
        f"**Target audience:** {target_audience}\n\n"
        f"**YouTube topic:** {search_topic}\n\n"
        f"**Selected creator:** {summary_creator.get('channel', '—')}\n\n"
        f"**Overall fit score:** {fit_score}\n\n"
        "## Generated brief\n\n"
        f"{st.session_state.get('generated_brief', 'Not started')}\n\n"
        "## Review result\n\n"
        f"{st.session_state.get('compliance_review', '—')}\n\n"
        "## Final decision\n\n"
        f"{saved_decision or '—'}\n\n"
        "## Reviewer notes\n\n"
        f"{st.session_state.get('reviewer_notes') or '—'}\n"
    )
    st.download_button(
        "Download campaign summary", data=campaign_markdown,
        file_name="creatorpulse_campaign_summary.md", mime="text/markdown",
    )

# Render after stage actions so the sidebar reflects changes immediately.
with st.sidebar:
    st.header("Campaign")
    st.write("**Mode:** Sample campaign" if st.session_state.get("demo_mode") else "**Mode:** Live data")
    if st.query_params.get("admin") == "1":
        if st.button("💾 Save demo snapshot"):
            try:
                saved_path = save_demo_snapshot()
                st.session_state["_saved_demo_json"] = saved_path.read_text(encoding="utf-8")
                st.success(f"Saved demo snapshot: {saved_path}")
            except (OSError, TypeError, ValueError) as error:
                st.error("Could not save the demo snapshot.")
                with st.expander("Technical details"):
                    st.code(str(error))
        if "_saved_demo_json" in st.session_state:
            st.download_button("Download demo snapshot", st.session_state["_saved_demo_json"],
                               file_name="demo_campaign.json", mime="application/json")
    st.write(f"**Brand:** {st.session_state.get('brand') or '—'}")
    st.write(f"**Topic:** {st.session_state.get('search_topic') or '—'}")
    sidebar_results = st.session_state.get("youtube_results")
    video_count = len(sidebar_results) if sidebar_results is not None else "—"
    st.write(f"**Videos found:** {video_count}")
    sidebar_creator = st.session_state.get("selected_creator", {})
    st.write(f"**Selected creator:** {sidebar_creator.get('channel', '—')}")
    sidebar_fit = next(
        (item for item in st.session_state.get("creator_fit_results", [])
         if item["channel"] == sidebar_creator.get("channel")), {},
    )
    sidebar_score = f"{sidebar_fit['overall_fit']}/100" if sidebar_fit else "—"
    st.write(f"**Fit score:** {sidebar_score}")
    brief_status = "Drafted" if st.session_state.get("generated_brief") else "Not started"
    st.write(f"**Brief status:** {brief_status}")
    review_status = "—"
    if st.session_state.get("compliance_review"):
        review_status = "Reviewed"
        for line in st.session_state["compliance_review"].splitlines():
            if line.strip().strip("*") in ("PASS", "REVISE", "BLOCK"):
                review_status = line.strip().strip("*")
                break
    if st.session_state.get("compliance_review", "").startswith("## Review method\n\nManual human review"):
        review_status = f"Manual · {review_status}"
    st.write(f"**Review status:** {review_status}")
    st.write(f"**Final decision:** {st.session_state.get('final_decision') or '—'}")
    for number, name in enumerate(STAGES, 1):
        if number < st.session_state.stage and stage_ready(number):
            st.button(
                f"✓ {name}", key=f"jump_stage_{number}",
                on_click=go_to_stage, args=(number,), use_container_width=True,
            )

back_column, next_column = st.columns(2)
with back_column:
    if st.session_state.stage > 1 and st.button("← Back"):
        st.session_state.stage -= 1
        st.rerun()
with next_column:
    if st.session_state.stage < 4:
        ready = stage_ready(st.session_state.stage)
        if st.button(f"Next: {STAGES[st.session_state.stage]} →", disabled=not ready):
            st.session_state.stage += 1
            st.rerun()
        if not ready:
            st.caption({
                1: "Find creator opportunities to continue.",
                2: "Choose a creator in Human Creator Selection to continue.",
                3: "Run Review Creator Draft or save a manual review to continue.",
            }[st.session_state.stage])
    else:
        st.button("Start a new campaign", on_click=start_new_campaign)
