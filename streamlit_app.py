import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import snowflake.connector

st.set_page_config(
    page_title="UrbanBrew Location Intelligence",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_connection():
    return snowflake.connector.connect(
        connection_name="bzrlvzw-mx84149",
        database="URBANBREW_LOCATION_INTEL",
        schema="ANALYTICS",
        client_store_temporary_credential=False,
    )


sf_conn = get_connection()


def run_query(sql):
    cur = sf_conn.cursor()
    cur.execute(sql)
    cols = [desc[0] for desc in cur.description]
    result = pd.DataFrame(cur.fetchall(), columns=cols)
    for col in result.columns:
        if result[col].dtype == object:
            try:
                result[col] = pd.to_numeric(result[col])
            except (ValueError, TypeError):
                pass
    return result


@st.cache_data(ttl=300)
def load_scorecard():
    return run_query("""
        SELECT * FROM URBANBREW_LOCATION_INTEL.ANALYTICS.LOCATION_SCORECARD
        ORDER BY OPPORTUNITY_SCORE DESC
    """)


@st.cache_data(ttl=300)
def load_competitors():
    return run_query("""
        SELECT * FROM URBANBREW_LOCATION_INTEL.RAW.COMPETITOR_CAFES
    """)


@st.cache_data(ttl=300)
def load_pois():
    return run_query("""
        SELECT * FROM URBANBREW_LOCATION_INTEL.RAW.COMMERCIAL_POIS
    """)


@st.cache_data(ttl=300)
def load_existing_stores():
    return run_query("""
        SELECT * FROM URBANBREW_LOCATION_INTEL.RAW.EXISTING_STORES
    """)


@st.cache_data(ttl=300)
def load_metro():
    return run_query("""
        SELECT * FROM URBANBREW_LOCATION_INTEL.RAW.METRO_STATIONS
    """)


def compute_weighted_score(row, weights):
    return round(
        weights["competition"] * float(row["COMPETITION_SCORE"])
        + weights["accessibility"] * float(row["ACCESSIBILITY_SCORE"])
        + weights["commercial"] * float(row["COMMERCIAL_ACTIVITY_SCORE"])
        + weights["purchasing_power"] * float(row["PURCHASING_POWER_SCORE"])
        + weights["demand"] * float(row["DEMAND_PROXY_SCORE"])
        + weights["cannibalization"] * float(row["CANNIBALIZATION_SCORE"]),
        1,
    )


df = load_scorecard()
df_competitors = load_competitors()
df_pois = load_pois()
df_stores = load_existing_stores()
df_metro = load_metro()

# --- Sidebar ---
st.sidebar.title("UrbanBrew Location Intelligence")
st.sidebar.caption("Next Store Location Analysis — Jaipur")

page = st.sidebar.radio(
    "Navigate",
    ["Scorecard", "Location Deep Dive", "Compare Locations", "Map View"],
)

st.sidebar.markdown("---")
st.sidebar.subheader("Scoring Weights")
w_comp = st.sidebar.slider("Competition", 0.0, 0.5, 0.20, 0.05)
w_acc = st.sidebar.slider("Accessibility", 0.0, 0.5, 0.15, 0.05)
w_comm = st.sidebar.slider("Commercial Activity", 0.0, 0.5, 0.25, 0.05)
w_pp = st.sidebar.slider("Purchasing Power", 0.0, 0.5, 0.15, 0.05)
w_dem = st.sidebar.slider("Demand Proxy", 0.0, 0.5, 0.15, 0.05)
w_can = st.sidebar.slider("Cannibalization", 0.0, 0.5, 0.10, 0.05)

total_weight = w_comp + w_acc + w_comm + w_pp + w_dem + w_can
if abs(total_weight - 1.0) > 0.01:
    st.sidebar.warning(f"Weights sum to {total_weight:.2f} (should be 1.0)")

weights = {
    "competition": w_comp,
    "accessibility": w_acc,
    "commercial": w_comm,
    "purchasing_power": w_pp,
    "demand": w_dem,
    "cannibalization": w_can,
}

df["CUSTOM_SCORE"] = df.apply(lambda r: compute_weighted_score(r, weights), axis=1)
df = df.sort_values("CUSTOM_SCORE", ascending=False).reset_index(drop=True)

# Grade based on custom score
def assign_grade(score):
    if score >= 70:
        return "A - Strong"
    elif score >= 50:
        return "B - Moderate"
    elif score >= 30:
        return "C - Investigate"
    return "D - Low"

df["CUSTOM_GRADE"] = df["CUSTOM_SCORE"].apply(assign_grade)


# ===================== PAGE: SCORECARD =====================
if page == "Scorecard":
    st.title("Location Scorecard")
    st.markdown("All 15 candidate locations ranked by **Opportunity Score** (custom weights applied).")

    top = df.iloc[0]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Top Location", top["LOCATION_NAME"])
    col2.metric("Score", f"{top['CUSTOM_SCORE']:.1f}/100")
    col3.metric("Area", top["AREA"])
    col4.metric("Grade", top["CUSTOM_GRADE"])

    st.markdown("---")

    display_cols = [
        "LOCATION_NAME", "AREA", "ZONE_TYPE",
        "COMPETITION_SCORE", "ACCESSIBILITY_SCORE",
        "COMMERCIAL_ACTIVITY_SCORE", "PURCHASING_POWER_SCORE",
        "DEMAND_PROXY_SCORE", "CANNIBALIZATION_SCORE",
        "CUSTOM_SCORE", "CUSTOM_GRADE",
    ]
    st.dataframe(
        df[display_cols].style.background_gradient(
            subset=["CUSTOM_SCORE"], cmap="RdYlGn", vmin=0, vmax=100
        ),
        use_container_width=True,
        height=560,
    )

    st.markdown("---")
    fig_bar = px.bar(
        df,
        x="LOCATION_NAME",
        y="CUSTOM_SCORE",
        color="CUSTOM_GRADE",
        color_discrete_map={
            "A - Strong": "#2ecc71",
            "B - Moderate": "#f39c12",
            "C - Investigate": "#e67e22",
            "D - Low": "#e74c3c",
        },
        title="Opportunity Score by Location",
        labels={"CUSTOM_SCORE": "Score", "LOCATION_NAME": "Location"},
    )
    fig_bar.update_layout(xaxis_tickangle=-45, height=400)
    st.plotly_chart(fig_bar, use_container_width=True)


# ===================== PAGE: DEEP DIVE =====================
elif page == "Location Deep Dive":
    st.title("Location Deep Dive")

    selected = st.selectbox(
        "Select a location",
        df["LOCATION_NAME"].tolist(),
    )
    loc = df[df["LOCATION_NAME"] == selected].iloc[0]

    col1, col2, col3 = st.columns(3)
    col1.metric("Opportunity Score", f"{loc['CUSTOM_SCORE']:.1f}")
    col2.metric("Grade", loc["CUSTOM_GRADE"])
    col3.metric("Zone Type", loc["ZONE_TYPE"])

    col4, col5, col6 = st.columns(3)
    col4.metric("Rent/sqft", f"Rs {loc['AVG_RENT_PER_SQFT']}")
    col5.metric("Nearest Metro", f"{loc['NEAREST_OPERATIONAL_METRO_KM']} km")
    col6.metric("Nearest UrbanBrew", f"{loc['NEAREST_URBANBREW_KM']} km")

    st.markdown("---")

    # Radar chart
    categories = [
        "Competition", "Accessibility", "Commercial\nActivity",
        "Purchasing\nPower", "Demand\nProxy", "Cannibalization",
    ]
    values = [
        loc["COMPETITION_SCORE"], loc["ACCESSIBILITY_SCORE"],
        loc["COMMERCIAL_ACTIVITY_SCORE"], loc["PURCHASING_POWER_SCORE"],
        loc["DEMAND_PROXY_SCORE"], loc["CANNIBALIZATION_SCORE"],
    ]
    values_closed = values + [values[0]]
    categories_closed = categories + [categories[0]]

    fig_radar = go.Figure()
    fig_radar.add_trace(go.Scatterpolar(
        r=values_closed,
        theta=categories_closed,
        fill="toself",
        name=selected,
        line_color="#29B5E8",
    ))
    fig_radar.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=False,
        title=f"Score Breakdown — {selected}",
        height=450,
    )
    st.plotly_chart(fig_radar, use_container_width=True)

    # Nearby details
    st.subheader("Nearby Competitors (within 1 km)")
    st.write(f"**{int(loc['COMPETITORS_WITHIN_1KM'])}** total | **{int(loc['DIRECT_COFFEE_COMPETITORS'])}** direct coffee competitors")

    st.subheader("Commercial POI Breakdown")
    poi_data = {
        "Category": ["Education", "Healthcare", "Hospitality", "Office/IT", "Retail"],
        "Count": [
            int(loc["EDUCATION_POIS"]),
            int(loc["HEALTHCARE_POIS"]),
            int(loc["HOSPITALITY_POIS"]),
            int(loc["OFFICE_IT_POIS"]),
            int(loc["RETAIL_POIS"]),
        ],
    }
    fig_poi = px.bar(
        pd.DataFrame(poi_data),
        x="Category",
        y="Count",
        color="Category",
        title=f"POIs within 1.5 km of {selected}",
    )
    st.plotly_chart(fig_poi, use_container_width=True)

    st.subheader("Purchasing Power Benchmark (2011 Census Proxy)")
    st.info("This is a historical benchmark based on H14 household asset data (2011 Census). It does NOT represent current income levels.")
    st.write(f"**Asset Index:** {loc['ASSET_INDEX']} | **Score:** {loc['PURCHASING_POWER_SCORE']:.1f}/100")


# ===================== PAGE: COMPARE =====================
elif page == "Compare Locations":
    st.title("Compare Locations")

    options = df["LOCATION_NAME"].tolist()
    selected_locs = st.multiselect(
        "Select 2-4 locations to compare",
        options,
        default=options[:3],
        max_selections=4,
    )

    if len(selected_locs) < 2:
        st.warning("Please select at least 2 locations.")
    else:
        comp_df = df[df["LOCATION_NAME"].isin(selected_locs)]

        score_cols = [
            "COMPETITION_SCORE", "ACCESSIBILITY_SCORE",
            "COMMERCIAL_ACTIVITY_SCORE", "PURCHASING_POWER_SCORE",
            "DEMAND_PROXY_SCORE", "CANNIBALIZATION_SCORE",
        ]
        labels = [
            "Competition", "Accessibility", "Commercial Activity",
            "Purchasing Power", "Demand Proxy", "Cannibalization",
        ]

        # Grouped bar chart
        melted = comp_df.melt(
            id_vars=["LOCATION_NAME"],
            value_vars=score_cols,
            var_name="Metric",
            value_name="Score",
        )
        melted["Metric"] = melted["Metric"].map(dict(zip(score_cols, labels)))

        fig_comp = px.bar(
            melted,
            x="Metric",
            y="Score",
            color="LOCATION_NAME",
            barmode="group",
            title="Sub-Score Comparison",
            labels={"LOCATION_NAME": "Location"},
            height=450,
        )
        st.plotly_chart(fig_comp, use_container_width=True)

        # Overlay radar
        fig_radar = go.Figure()
        colors = ["#29B5E8", "#FF6B6B", "#4ECB71", "#FFA726"]
        for i, (_, row) in enumerate(comp_df.iterrows()):
            vals = [row[c] for c in score_cols] + [row[score_cols[0]]]
            cats = labels + [labels[0]]
            fig_radar.add_trace(go.Scatterpolar(
                r=vals, theta=cats, fill="toself",
                name=row["LOCATION_NAME"],
                line_color=colors[i % len(colors)],
            ))
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            title="Radar Comparison",
            height=450,
        )
        st.plotly_chart(fig_radar, use_container_width=True)

        # Summary table
        summary_cols = ["LOCATION_NAME", "AREA", "CUSTOM_SCORE", "CUSTOM_GRADE",
                        "COMPETITORS_WITHIN_1KM", "NEAREST_OPERATIONAL_METRO_KM",
                        "NEAREST_URBANBREW_KM", "AVG_RENT_PER_SQFT"]
        st.dataframe(comp_df[summary_cols], use_container_width=True)


# ===================== PAGE: MAP VIEW =====================
elif page == "Map View":
    st.title("Jaipur Location Map")
    st.markdown("Candidate locations, existing UrbanBrew stores, competitors, and metro stations.")

    # Score-based color
    def score_color(score):
        if score >= 70:
            return [46, 204, 113, 180]
        elif score >= 50:
            return [243, 156, 18, 180]
        elif score >= 30:
            return [230, 126, 34, 180]
        return [231, 76, 60, 180]

    map_df = df[["LOCATION_NAME", "LAT", "LON", "CUSTOM_SCORE", "CUSTOM_GRADE", "AREA"]].copy()
    map_df["color"] = map_df["CUSTOM_SCORE"].apply(score_color)
    map_df["size"] = map_df["CUSTOM_SCORE"] * 5 + 200

    # Use plotly scattermapbox for richer map
    fig_map = go.Figure()

    # Candidate locations
    fig_map.add_trace(go.Scattermap(
        lat=map_df["LAT"],
        lon=map_df["LON"],
        mode="markers+text",
        marker=dict(
            size=14,
            color=map_df["CUSTOM_SCORE"],
            colorscale="RdYlGn",
            cmin=0,
            cmax=100,
            colorbar=dict(title="Score"),
        ),
        text=map_df["LOCATION_NAME"],
        textposition="top center",
        name="Candidate Locations",
        hovertemplate="<b>%{text}</b><br>Score: %{marker.color:.1f}<extra></extra>",
    ))

    # Existing stores
    fig_map.add_trace(go.Scattermap(
        lat=df_stores["LAT"],
        lon=df_stores["LON"],
        mode="markers",
        marker=dict(size=12, color="#8B4513", symbol="circle"),
        text=df_stores["STORE_NAME"],
        name="Existing UrbanBrew",
        hovertemplate="<b>%{text}</b><br>(Existing Store)<extra></extra>",
    ))

    # Metro stations
    operational = df_metro[df_metro["STATUS"] == "Operational"]
    fig_map.add_trace(go.Scattermap(
        lat=operational["LAT"],
        lon=operational["LON"],
        mode="markers",
        marker=dict(size=8, color="#9B59B6", symbol="circle"),
        text=operational["STATION_NAME"],
        name="Metro (Operational)",
        hovertemplate="<b>%{text}</b><br>Metro Station<extra></extra>",
    ))

    fig_map.update_layout(
        map=dict(
            style="open-street-map",
            center=dict(lat=26.89, lon=75.80),
            zoom=11,
        ),
        height=650,
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )
    st.plotly_chart(fig_map, use_container_width=True)

    # Legend
    col1, col2, col3, col4 = st.columns(4)
    col1.markdown("**Green** = Score >= 70 (A)")
    col2.markdown("**Yellow** = Score 50-69 (B)")
    col3.markdown("**Orange** = Score 30-49 (C)")
    col4.markdown("**Red** = Score < 30 (D)")


# --- Footer ---
st.sidebar.markdown("---")
st.sidebar.caption(
    "Data sources: Simulated from Jaipur OSM geography. "
    "Purchasing power is a 2011 Census benchmark (H14 household assets), not current income."
)
