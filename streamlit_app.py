import streamlit as st
from google import genai

st.set_page_config(
    page_title="CreatorPulse",
    page_icon="🚀",
    layout="wide"
)

st.title("🚀 CreatorPulse")
st.subheader("AI-powered creator campaign accelerator")
st.write("NYU SPS x Google Hackathon prototype")

# Safely read the Gemini key from Streamlit Secrets
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

# Connect to Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

st.success("CreatorPulse is running successfully!")

if st.button("Test Gemini"):
    with st.spinner("Asking Gemini..."):
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents="In one sentence, explain what creator marketing is."
        )

        st.write(response.text)
