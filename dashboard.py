import streamlit as st
import requests


API_URL = "http://127.0.0.1:8000/api/decision"


st.set_page_config(
    page_title="Adaptive Smart QoS",
    page_icon="🌐",
    layout="wide"
)


# --------------------------------------------------
# PAGE HEADER
# --------------------------------------------------

st.title("🌐 Adaptive Smart QoS")
st.subheader("Multi-Factor Decision Engine")

st.write(
    "Analyze network conditions and dynamically determine "
    "the appropriate QoS policy."
)


# --------------------------------------------------
# INPUT SECTION
# --------------------------------------------------

st.markdown("## 📥 Network Conditions")

col1, col2 = st.columns(2)

with col1:
    traffic_type = st.selectbox(
        "Traffic Type",
        [
            "Video Call",
            "Voice Call",
            "Gaming",
            "Web Browsing",
            "File Download",
            "Background Traffic",
            "Suspicious Traffic"
        ]
    )

    threat_level = st.slider(
        "Threat Level",
        min_value=0.0,
        max_value=10.0,
        value=2.0,
        step=0.5,
        help="0 = No threat, 10 = Extremely high threat"
    )

    congestion = st.slider(
        "Network Congestion",
        min_value=0.0,
        max_value=10.0,
        value=3.0,
        step=0.5,
        help="0 = No congestion, 10 = Severe congestion"
    )

    bandwidth = st.number_input(
        "Available Bandwidth (Mbps)",
        min_value=0.0,
        value=20.0,
        step=1.0
    )


with col2:
    application_priority = st.slider(
        "Application Priority",
        min_value=0.0,
        max_value=10.0,
        value=8.0,
        step=0.5,
        help="0 = Very low, 10 = Critical"
    )

    device_trust = st.slider(
        "Device Trust Score",
        min_value=0.0,
        max_value=100.0,
        value=90.0,
        step=5.0,
        help="0 = Untrusted, 100 = Highly trusted"
    )

    latency = st.number_input(
        "Latency (ms)",
        min_value=0.0,
        value=50.0,
        step=5.0
    )


# --------------------------------------------------
# ANALYZE BUTTON
# --------------------------------------------------

st.markdown("---")

analyze = st.button(
    "🚀 ANALYZE NETWORK",
    use_container_width=True
)


# --------------------------------------------------
# SEND DATA TO FASTAPI
# --------------------------------------------------

if analyze:

    request_data = {
        "traffic_type": traffic_type,
        "threat_level": threat_level,
        "congestion": congestion,
        "bandwidth_available": bandwidth,
        "application_priority": application_priority,
        "device_trust": device_trust,
        "latency": latency
    }

    try:

        response = requests.post(
            API_URL,
            json=request_data,
            timeout=5
        )

        if response.status_code == 200:

            result = response.json()

            st.markdown("## 🧠 Decision Engine Result")

            # ------------------------------------------
            # MAIN RESULTS
            # ------------------------------------------

            r1, r2, r3 = st.columns(3)

            with r1:
                st.metric(
                    "Decision Score",
                    f"{result['decision_score']:.2f}"
                )

            with r2:
                st.metric(
                    "Priority",
                    result["priority"]
                )

            with r3:
                st.metric(
                    "QoS Policy",
                    result["qos_policy"]
                )


            r4, r5, r6 = st.columns(3)

            with r4:
                st.metric(
                    "Bandwidth Allocation",
                    f"{result['bandwidth_allocation']} Mbps"
                )

            with r5:
                st.metric(
                    "Queue",
                    result["queue"]
                )

            with r6:
                st.metric(
                    "Security Action",
                    result["security_action"]
                )


            # ------------------------------------------
            # EXPLANATION
            # ------------------------------------------

            st.markdown("### 💡 Why did the system make this decision?")

            st.info(result["reason"])


        else:

            st.error(
                f"API returned an error: {response.status_code}"
            )

            st.write(response.text)


    except requests.exceptions.ConnectionError:

        st.error(
            "❌ Cannot connect to the FastAPI server. "
            "Make sure Uvicorn is running."
        )

    except Exception as error:

        st.error(f"Unexpected error: {error}")