from __future__ import annotations

from pathlib import Path

import streamlit as st

from market_analytics.io import load_and_validate_dataset
from market_analytics.reporting import build_analytics_outputs


def render_summary_metrics(summary_frame, *, labels: tuple[str, str, str, str]) -> None:
    summary = summary_frame.set_index("metric")["value"]
    metric_columns = st.columns(4)
    metric_columns[0].metric(labels[0], int(summary["distinct_items"]))
    metric_columns[1].metric(labels[1], int(summary["total_mentions"]))
    metric_columns[2].metric(labels[2], int(summary["vacancies_with_items"]))
    metric_columns[3].metric(labels[3], f"{float(summary['vacancy_coverage']):.1%}")


st.set_page_config(page_title="Swiss IT Job Analytics", layout="wide")
st.title("Swiss IT Job Market Analytics")
st.caption("Load a processed jobs.ch dataset and inspect high-level market distributions.")

dataset_path = st.sidebar.text_input(
    "Dataset path",
    value="",
    help="Absolute or project-relative path to a CSV, Parquet, SQLite, JSON, or JSONL dataset.",
)
top_skills_limit = st.sidebar.slider("Top skills limit", min_value=5, max_value=50, value=20)
top_pairs_limit = st.sidebar.slider(
    "Top co-occurrence pairs",
    min_value=10,
    max_value=100,
    value=50,
    step=5,
)

if not dataset_path.strip():
    st.info("Enter a dataset path in the sidebar to load analytics.")
    st.stop()

try:
    dataset = load_and_validate_dataset(Path(dataset_path))
    outputs = build_analytics_outputs(
        dataset=dataset,
        top_skills_limit=top_skills_limit,
        top_skill_pairs_limit=top_pairs_limit,
    )
except Exception as exc:
    st.error(str(exc))
    st.stop()

overview = outputs["overview_metrics"].set_index("metric")["value"]
metric_columns = st.columns(3)
metric_columns[0].metric("Total vacancies", int(overview["total_vacancies"]))
metric_columns[1].metric("Total companies", int(overview["total_companies"]))
metric_columns[2].metric(
    "Avg vacancies / company",
    float(overview["average_vacancies_per_company"]),
)

st.subheader("Distributions")
for output_name in (
    "distribution_role_category",
    "distribution_city",
    "distribution_canton",
    "distribution_seniority",
    "distribution_work_mode",
):
    frame = outputs[output_name]
    dimension = output_name.removeprefix("distribution_")
    st.markdown(f"**{dimension.replace('_', ' ').title()}**")
    st.bar_chart(frame.head(15).set_index(dimension)["vacancy_count"])
    st.dataframe(frame, use_container_width=True, hide_index=True)

st.subheader("Skills")
st.markdown("**Top skills overall**")
st.dataframe(outputs["top_skills_overall"], use_container_width=True, hide_index=True)

skill_columns = st.columns(2)
with skill_columns[0]:
    st.markdown("**Top skills by role category**")
    st.dataframe(
        outputs["top_skills_by_role_category"],
        use_container_width=True,
        hide_index=True,
    )
with skill_columns[1]:
    st.markdown("**Top skills by canton**")
    st.dataframe(outputs["top_skills_by_canton"], use_container_width=True, hide_index=True)

st.markdown("**Skill co-occurrence pairs**")
st.dataframe(outputs["skill_cooccurrence_pairs"], use_container_width=True, hide_index=True)

st.subheader("Programming Languages")
render_summary_metrics(
    outputs["programming_languages_summary"],
    labels=(
        "Unique languages",
        "Total mentions",
        "Vacancies with languages",
        "Coverage",
    ),
)
st.bar_chart(
    outputs["top_programming_languages"]
    .set_index("programming_language")["vacancy_count"]
    if not outputs["top_programming_languages"].empty
    else outputs["top_programming_languages"]
)
st.dataframe(outputs["top_programming_languages"], use_container_width=True, hide_index=True)

st.subheader("Frameworks and Libraries")
render_summary_metrics(
    outputs["frameworks_libraries_summary"],
    labels=(
        "Unique frameworks",
        "Total mentions",
        "Vacancies with frameworks",
        "Coverage",
    ),
)
st.bar_chart(
    outputs["top_frameworks_libraries"]
    .set_index("framework_library")["vacancy_count"]
    if not outputs["top_frameworks_libraries"].empty
    else outputs["top_frameworks_libraries"]
)
st.dataframe(outputs["top_frameworks_libraries"], use_container_width=True, hide_index=True)

st.subheader("Crosstabs")
st.markdown("**Role category vs seniority**")
st.dataframe(
    outputs["crosstab_role_category_vs_seniority"],
    use_container_width=True,
    hide_index=True,
)

st.markdown("**Role category vs work mode**")
st.dataframe(
    outputs["crosstab_role_category_vs_work_mode"],
    use_container_width=True,
    hide_index=True,
)
