import streamlit as st
import requests
import pandas as pd

from src.adaptive_simulator import run_adaptive_simulation


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Adaptive Smart QoS",
    page_icon="🌐",
    layout="wide"
)


# ============================================================
# SESSION STATE
# ============================================================

if "decision_history" not in st.session_state:
    st.session_state.decision_history = []

if "last_result" not in st.session_state:
    st.session_state.last_result = None


# ============================================================
# API CONFIGURATION
# ============================================================

API_URL = "http://127.0.0.1:8000/api/decision"


# ============================================================
# HEADER
# ============================================================

st.title("🌐 Adaptive Smart QoS")
st.subheader("Multi-Factor Decision Engine")

st.write(
    "Analyze network conditions and dynamically determine "
    "the appropriate QoS policy using multiple network, "
    "application, security, and device factors."
)


# ============================================================
# SECTION 1 — NETWORK INPUT
# ============================================================

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


# ============================================================
# ANALYZE NETWORK
# ============================================================

st.markdown("---")

analyze = st.button(
    "🚀 ANALYZE NETWORK",
    use_container_width=True
)


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

            # Store latest result
            st.session_state.last_result = result

            # Store decision history
            st.session_state.decision_history.append({
                "Traffic Type": traffic_type,
                "Threat": threat_level,
                "Congestion": congestion,
                "Bandwidth (Mbps)": bandwidth,
                "Latency (ms)": latency,
                "Score": result["decision_score"],
                "Priority": result["priority"],
                "Policy": result["qos_policy"],
                "Security": result["security_action"]
            })


            # ==================================================
            # DECISION ENGINE RESULT
            # ==================================================

            st.markdown("## 🧠 Decision Engine Result")

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


            # ==================================================
            # DECISION EXPLANATION
            # ==================================================

            st.markdown(
                "### 💡 Why did the system make this decision?"
            )

            st.info(result["reason"])


            # ==================================================
            # FACTOR CONTRIBUTIONS
            # ==================================================

            st.markdown(
                "### 📊 Decision Factor Contributions"
            )

            contributions = result.get(
                "factor_contributions",
                {}
            )

            if contributions:

                contribution_data = {
                    "Factor": [
                        factor.replace("_", " ").title()
                        for factor in contributions.keys()
                    ],
                    "Contribution": [
                        value
                        for value in contributions.values()
                    ]
                }

                contribution_df = pd.DataFrame(
                    contribution_data
                )

                st.dataframe(
                    contribution_df,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.info(
                    "Factor contribution data is not available."
                )


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

        st.error(
            f"Unexpected error: {error}"
        )


# ============================================================
# SECTION 2 — SCENARIO SIMULATOR
# ============================================================

st.markdown("---")

st.markdown("## 🧪 Scenario Simulator")

st.write(
    "Test how the Adaptive Smart QoS engine responds "
    "to different network and security conditions."
)


scenarios = {

    "Normal Video Call": {
        "traffic_type": "Video Call",
        "threat_level": 2,
        "congestion": 3,
        "bandwidth_available": 20,
        "application_priority": 8,
        "device_trust": 90,
        "latency": 50
    },

    "High Threat Traffic": {
        "traffic_type": "Suspicious Traffic",
        "threat_level": 9,
        "congestion": 4,
        "bandwidth_available": 30,
        "application_priority": 9,
        "device_trust": 20,
        "latency": 60
    },

    "Severe Network Congestion": {
        "traffic_type": "Video Call",
        "threat_level": 2,
        "congestion": 9,
        "bandwidth_available": 15,
        "application_priority": 9,
        "device_trust": 90,
        "latency": 180
    },

    "Low Bandwidth": {
        "traffic_type": "File Download",
        "threat_level": 1,
        "congestion": 5,
        "bandwidth_available": 5,
        "application_priority": 4,
        "device_trust": 80,
        "latency": 100
    },

    "Low-Latency Gaming": {
        "traffic_type": "Gaming",
        "threat_level": 1,
        "congestion": 4,
        "bandwidth_available": 25,
        "application_priority": 9,
        "device_trust": 95,
        "latency": 30
    }
}


selected_scenario = st.selectbox(
    "Select a Scenario",
    list(scenarios.keys()),
    key="scenario_selector"
)


if st.button(
    "▶️ RUN SCENARIO",
    use_container_width=True
):

    scenario_data = scenarios[selected_scenario]

    try:

        response = requests.post(
            API_URL,
            json=scenario_data,
            timeout=5
        )

        if response.status_code == 200:

            result = response.json()

            st.markdown("### 📋 Scenario Result")

            s1, s2, s3 = st.columns(3)

            with s1:
                st.metric(
                    "Decision Score",
                    f"{result['decision_score']:.2f}"
                )

            with s2:
                st.metric(
                    "Priority",
                    result["priority"]
                )

            with s3:
                st.metric(
                    "QoS Policy",
                    result["qos_policy"]
                )


            s4, s5, s6 = st.columns(3)

            with s4:
                st.metric(
                    "Bandwidth",
                    f"{result['bandwidth_allocation']} Mbps"
                )

            with s5:
                st.metric(
                    "Queue",
                    result["queue"]
                )

            with s6:
                st.metric(
                    "Security",
                    result["security_action"]
                )


            st.markdown("### 💡 Decision Explanation")

            st.info(result["reason"])


        else:

            st.error(
                f"API returned an error: {response.status_code}"
            )


    except requests.exceptions.ConnectionError:

        st.error(
            "❌ Cannot connect to the FastAPI server."
        )


    except Exception as error:

        st.error(
            f"Simulation error: {error}"
        )


# ============================================================
# SECTION 3 — STATIC VS ADAPTIVE QOS
# ============================================================

st.markdown("---")

st.markdown("## ⚖️ Static QoS vs Adaptive QoS")

st.write(
    "Compare a fixed QoS policy with the adaptive decision "
    "produced by the Multi-Factor Decision Engine."
)


comparison_scenarios = {

    "Normal Video Call": {
        "traffic_type": "Video Call",
        "threat_level": 2,
        "congestion": 3,
        "bandwidth_available": 20,
        "application_priority": 8,
        "device_trust": 90,
        "latency": 50
    },

    "High Threat Traffic": {
        "traffic_type": "Suspicious Traffic",
        "threat_level": 9,
        "congestion": 4,
        "bandwidth_available": 30,
        "application_priority": 9,
        "device_trust": 20,
        "latency": 60
    },

    "Severe Congestion": {
        "traffic_type": "Video Call",
        "threat_level": 2,
        "congestion": 9,
        "bandwidth_available": 15,
        "application_priority": 9,
        "device_trust": 90,
        "latency": 180
    },

    "Low Bandwidth": {
        "traffic_type": "File Download",
        "threat_level": 1,
        "congestion": 5,
        "bandwidth_available": 5,
        "application_priority": 4,
        "device_trust": 80,
        "latency": 100
    }
}


comparison_scenario = st.selectbox(
    "Select Comparison Scenario",
    list(comparison_scenarios.keys()),
    key="comparison_scenario"
)


if st.button(
    "⚖️ RUN COMPARISON",
    use_container_width=True
):

    scenario = comparison_scenarios[
        comparison_scenario
    ]

    try:

        response = requests.post(
            API_URL,
            json=scenario,
            timeout=5
        )

        if response.status_code == 200:

            adaptive_result = response.json()


            # Static baseline
            static_policy = "NORMAL"
            static_priority = "NORMAL"


            st.markdown("### 📊 Comparison Result")

            c1, c2 = st.columns(2)


            with c1:

                st.markdown("#### 🔒 Static QoS")

                st.metric(
                    "Priority",
                    static_priority
                )

                st.metric(
                    "Policy",
                    static_policy
                )

                st.write(
                    "Fixed policy applied without adapting "
                    "to current network conditions."
                )


            with c2:

                st.markdown("#### 🧠 Adaptive QoS")

                st.metric(
                    "Priority",
                    adaptive_result["priority"]
                )

                st.metric(
                    "Policy",
                    adaptive_result["qos_policy"]
                )

                st.write(
                    "Policy dynamically selected using "
                    "multiple network and security factors."
                )


            st.markdown("### 🔍 Adaptive Decision")

            st.info(
                adaptive_result["reason"]
            )


        else:

            st.error(
                f"API returned an error: {response.status_code}"
            )


    except requests.exceptions.ConnectionError:

        st.error(
            "❌ Cannot connect to the FastAPI server."
        )


    except Exception as error:

        st.error(
            f"Comparison error: {error}"
        )


# ============================================================
# SECTION 4 — DECISION HISTORY
# ============================================================

st.markdown("---")

st.markdown("## 🕒 Decision History")

if st.session_state.decision_history:

    history_df = pd.DataFrame(
        st.session_state.decision_history
    )

    st.dataframe(
        history_df,
        use_container_width=True,
        hide_index=True
    )


    if st.button(
        "🗑️ Clear Decision History"
    ):

        st.session_state.decision_history = []

        st.rerun()

else:

    st.info(
        "No decisions recorded yet. "
        "Run an analysis to build history."
    )


# ============================================================
# SECTION 5 — ADAPTIVE BANDWIDTH ALLOCATION
# ============================================================

st.markdown("---")

st.markdown("## 📡 Adaptive Bandwidth Allocation")

st.write(
    "Visualize the bandwidth allocated by the decision "
    "engine for the latest network condition."
)


if (
    st.session_state.decision_history
    and st.session_state.last_result is not None
):

    latest_decision = (
        st.session_state.decision_history[-1]
    )

    available_bandwidth = latest_decision[
        "Bandwidth (Mbps)"
    ]

    allocated_bandwidth = (
        st.session_state.last_result[
            "bandwidth_allocation"
        ]
    )

    remaining_bandwidth = max(
        available_bandwidth - allocated_bandwidth,
        0
    )


    bandwidth_data = pd.DataFrame({
        "Bandwidth": [
            "Allocated",
            "Remaining"
        ],
        "Mbps": [
            allocated_bandwidth,
            remaining_bandwidth
        ]
    })


    st.bar_chart(
        bandwidth_data.set_index("Bandwidth")
    )


    st.metric(
        "Recommended Allocation",
        f"{allocated_bandwidth} Mbps"
    )


else:

    st.info(
        "Run a network analysis first."
    )


# ============================================================
# SECTION 6 — CLOSED-LOOP ADAPTIVE SIMULATION
# ============================================================

st.markdown("---")

st.markdown("## 🔄 Adaptive Network Simulation")

st.write(
    "Simulate changing network conditions and observe "
    "how the Adaptive Smart QoS engine responds over time."
)


simulation_scenarios = [

    {
        "traffic_type": "Video Call",
        "threat_level": 1,
        "congestion": 2,
        "bandwidth_available": 50,
        "application_priority": 8,
        "device_trust": 90,
        "latency": 40
    },

    {
        "traffic_type": "Video Call",
        "threat_level": 1,
        "congestion": 5,
        "bandwidth_available": 35,
        "application_priority": 8,
        "device_trust": 90,
        "latency": 80
    },

    {
        "traffic_type": "Video Call",
        "threat_level": 2,
        "congestion": 9,
        "bandwidth_available": 15,
        "application_priority": 9,
        "device_trust": 90,
        "latency": 180
    },

    {
        "traffic_type": "Video Call",
        "threat_level": 9,
        "congestion": 8,
        "bandwidth_available": 15,
        "application_priority": 9,
        "device_trust": 20,
        "latency": 200
    },

    {
        "traffic_type": "Video Call",
        "threat_level": 2,
        "congestion": 3,
        "bandwidth_available": 40,
        "application_priority": 8,
        "device_trust": 90,
        "latency": 50
    }
]


if st.button(
    "🔄 RUN ADAPTIVE SIMULATION",
    use_container_width=True
):

    try:

        simulation_results = run_adaptive_simulation(
            simulation_scenarios
        )


        # ======================================================
        # SIMULATION TABLE
        # ======================================================

        st.markdown("### 📊 Simulation Results")

        simulation_df = pd.DataFrame(
            simulation_results
        )

        st.dataframe(
            simulation_df,
            use_container_width=True,
            hide_index=True
        )


        # ======================================================
        # DECISION SCORE GRAPH
        # ======================================================

        st.markdown(
            "### 📈 Decision Score Over Time"
        )

        score_chart = simulation_df[
            ["Time Step", "Decision Score"]
        ].set_index("Time Step")

        st.line_chart(
            score_chart
        )


        # ======================================================
        # BANDWIDTH GRAPH
        # ======================================================

        st.markdown(
            "### 📡 Bandwidth Allocation Over Time"
        )

        bandwidth_chart = simulation_df[
            ["Time Step", "Bandwidth Allocation"]
        ].set_index("Time Step")

        st.line_chart(
            bandwidth_chart
        )


        # ======================================================
        # SIMULATION SUMMARY
        # ======================================================

        st.markdown("### 📌 Simulation Summary")


        initial_score = simulation_df.iloc[0][
            "Decision Score"
        ]

        final_score = simulation_df.iloc[-1][
            "Decision Score"
        ]

        max_congestion = simulation_df[
            "Congestion"
        ].max()

        max_threat = simulation_df[
            "Threat"
        ].max()


        restricted_steps = simulation_df[
            simulation_df["Security Action"].isin(
                [
                    "RESTRICT",
                    "QUARANTINE"
                ]
            )
        ]


        s1, s2, s3, s4 = st.columns(4)


        with s1:

            st.metric(
                "Initial Score",
                f"{initial_score:.2f}"
            )


        with s2:

            st.metric(
                "Final Score",
                f"{final_score:.2f}"
            )


        with s3:

            st.metric(
                "Peak Congestion",
                f"{max_congestion:.1f}/10"
            )


        with s4:

            st.metric(
                "Peak Threat",
                f"{max_threat:.1f}/10"
            )


        st.write(
            f"Security-restricted steps: "
            f"**{len(restricted_steps)}**"
        )


    except Exception as error:

        st.error(
            f"Simulation error: {error}"
        )