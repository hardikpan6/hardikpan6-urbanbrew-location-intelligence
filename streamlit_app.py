import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

st.set_page_config(
    page_title="UrbanBrew Location Intelligence",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def minmax_score(series, invert=False):
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(50.0, index=series.index)
    normed = (series - mn) / (mx - mn)
    if invert:
        normed = 1 - normed
    return (normed * 100).round(1)


@st.cache_data
def load_and_score():
    candidates = pd.read_csv(os.path.join(DATA_DIR, "candidate_locations.csv"))
    competitors = pd.read_csv(os.path.join(DATA_DIR, "competitor_cafes.csv"))
    metro = pd.read_csv(os.path.join(DATA_DIR, "metro_stations.csv"))
    pois = pd.read_csv(os.path.join(DATA_DIR, "commercial_pois.csv"))
    stores = pd.read_csv(os.path.join(DATA_DIR, "existing_stores.csv"))
    assets = pd.read_csv(os.path.join(DATA_DIR, "household_assets_2011.csv"))

    # Uppercase column names to match existing UI code
    for frame in [candidates, competitors, metro, pois, stores, assets]:
        frame.columns = [c.upper() for c in frame.columns]

    rows = []
    for _, cl in candidates.iterrows():
        # --- Competition ---
        dists_comp = competitors.apply(
            lambda c: haversine_km(cl["LAT"], cl["LON"], c["LAT"], c["LON"]), axis=1
        )
        nearby = competitors[dists_comp <= 1.0]
        comp_count = len(nearby)
        direct_coffee = len(
            nearby[
                (nearby["TYPE"] == "Cafe")
                & nearby["CUISINE_OR_CATEGORY"].isin(["Coffee Chain", "Specialty Coffee"])
            ]
        )

        # --- Accessibility ---
        dists_metro = metro.apply(
            lambda m: haversine_km(cl["LAT"], cl["LON"], m["LAT"], m["LON"]), axis=1
        )
        op_mask = metro["STATUS"] == "Operational"
        nearest_op_metro = dists_metro[op_mask].min() if op_mask.any() else np.nan
        ridership_nearby = metro[(dists_metro <= 2.0) & op_mask]
        max_ridership = int(ridership_nearby["DAILY_RIDERSHIP_ESTIMATE"].max()) if len(ridership_nearby) else 0

        # --- Commercial Activity ---
        dists_poi = pois.apply(
            lambda p: haversine_km(cl["LAT"], cl["LON"], p["LAT"], p["LON"]), axis=1
        )
        nearby_pois = pois[dists_poi <= 1.5]
        cat_counts = nearby_pois["CATEGORY"].value_counts()
        edu = int(cat_counts.get("Education", 0))
        hc = int(cat_counts.get("Healthcare", 0))
        hosp = int(cat_counts.get("Hospitality", 0))
        off = int(cat_counts.get("Office-IT", 0))
        ret = int(cat_counts.get("Retail-Mall", 0))
        ent = int(cat_counts.get("Entertainment", 0))
        tour = int(cat_counts.get("Tourism", 0))
        trans = int(cat_counts.get("Transport", 0))
        weighted_poi = (
            edu * 1.2 + hc * 0.8 + hosp * 1.5 + off * 2.0
            + ret * 1.8 + ent * 1.3 + tour * 1.0 + trans * 1.5
        )

        # --- Purchasing Power ---
        area_match = assets[assets["AREA_NAME"] == cl["AREA"]]
        asset_index = float(area_match["ASSET_INDEX"].iloc[0]) if len(area_match) else 0.0

        # --- Cannibalization ---
        dists_stores = stores.apply(
            lambda s: haversine_km(cl["LAT"], cl["LON"], s["LAT"], s["LON"]), axis=1
        )
        nearest_idx = dists_stores.idxmin()
        nearest_ub_km = round(dists_stores[nearest_idx], 2)
        nearest_store_name = stores.loc[nearest_idx, "STORE_NAME"]

        rows.append({
            "LOCATION_ID": cl["LOCATION_ID"],
            "LOCATION_NAME": cl["LOCATION_NAME"],
            "AREA": cl["AREA"],
            "ZONE_TYPE": cl["ZONE_TYPE"],
            "AVG_RENT_PER_SQFT": cl["AVG_RENT_PER_SQFT"],
            "FOOTFALL_ESTIMATE_CATEGORY": cl["FOOTFALL_ESTIMATE_CATEGORY"],
            "LAT": cl["LAT"],
            "LON": cl["LON"],
            "COMPETITORS_WITHIN_1KM": comp_count,
            "DIRECT_COFFEE_COMPETITORS": direct_coffee,
            "NEAREST_OPERATIONAL_METRO_KM": round(nearest_op_metro, 2) if pd.notna(nearest_op_metro) else None,
            "MAX_NEARBY_RIDERSHIP": max_ridership,
            "EDUCATION_POIS": edu,
            "HEALTHCARE_POIS": hc,
            "HOSPITALITY_POIS": hosp,
            "OFFICE_IT_POIS": off,
            "RETAIL_POIS": ret,
            "WEIGHTED_POI": weighted_poi,
            "ASSET_INDEX": asset_index,
            "NEAREST_URBANBREW_KM": nearest_ub_km,
            "NEAREST_STORE_NAME": nearest_store_name,
        })

    df = pd.DataFrame(rows)

    # Min-max normalization scores
    df["COMPETITION_SCORE"] = minmax_score(df["COMPETITORS_WITHIN_1KM"], invert=True)
    df["ACCESSIBILITY_SCORE"] = minmax_score(df["NEAREST_OPERATIONAL_METRO_KM"], invert=True)
    df["COMMERCIAL_ACTIVITY_SCORE"] = minmax_score(df["WEIGHTED_POI"])
    df["PURCHASING_POWER_SCORE"] = minmax_score(df["ASSET_INDEX"])
    df["CANNIBALIZATION_SCORE"] = minmax_score(df["NEAREST_URBANBREW_KM"])

    # Demand proxy = 0.65 * commercial + 0.35 * accessibility
    df["DEMAND_PROXY_SCORE"] = (0.65 * df["COMMERCIAL_ACTIVITY_SCORE"] + 0.35 * df["ACCESSIBILITY_SCORE"]).round(1)

    # Default opportunity score
    df["OPPORTUNITY_SCORE"] = (
        0.20 * df["COMPETITION_SCORE"]
        + 0.15 * df["ACCESSIBILITY_SCORE"]
        + 0.25 * df["COMMERCIAL_ACTIVITY_SCORE"]
        + 0.15 * df["PURCHASING_POWER_SCORE"]
        + 0.15 * df["DEMAND_PROXY_SCORE"]
        + 0.10 * df["CANNIBALIZATION_SCORE"]
    ).round(1)

    return df, competitors, pois, stores, metro


df, df_competitors, df_pois, df_stores, df_metro = load_and_score()


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

        summary_cols = ["LOCATION_NAME", "AREA", "CUSTOM_SCORE", "CUSTOM_GRADE",
                        "COMPETITORS_WITHIN_1KM", "NEAREST_OPERATIONAL_METRO_KM",
                        "NEAREST_URBANBREW_KM", "AVG_RENT_PER_SQFT"]
        st.dataframe(comp_df[summary_cols], use_container_width=True)


# ===================== PAGE: MAP VIEW =====================
elif page == "Map View":
    st.title("Jaipur Location Map")
    st.markdown("Candidate locations, existing UrbanBrew stores, competitors, and metro stations.")

    map_df = df[["LOCATION_NAME", "LAT", "LON", "CUSTOM_SCORE", "CUSTOM_GRADE", "AREA"]].copy()

    fig_map = go.Figure()

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

    fig_map.add_trace(go.Scattermap(
        lat=df_stores["LAT"],
        lon=df_stores["LON"],
        mode="markers",
        marker=dict(size=12, color="#8B4513", symbol="circle"),
        text=df_stores["STORE_NAME"],
        name="Existing UrbanBrew",
        hovertemplate="<b>%{text}</b><br>(Existing Store)<extra></extra>",
    ))

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
