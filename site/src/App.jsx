import { useEffect, useState } from "react";

import dotUrl from "./assets/images/arrow-badge-right.svg";
import flagUrl from "./assets/images/flag.png";
const heroDotsUrl =
  "https://cdn.prod.website-files.com/6961d185cb919d4c701e9c24/6961f78138e472cb2803976f_Group%201.png";
const heroCornerTopLeft =
  "https://cdn.prod.website-files.com/6961d185cb919d4c701e9c24/6961f5c5148bf83c7ddae34f_Group%203.svg";
const heroCornerTopRight =
  "https://cdn.prod.website-files.com/6961d185cb919d4c701e9c24/6961f5c550ae5835d32a7cdb_Group%205.svg";
const heroCornerBottomLeft =
  "https://cdn.prod.website-files.com/6961d185cb919d4c701e9c24/6961f5c52d02027389981aa2_Group%204.svg";
const heroCornerBottomRight =
  "https://cdn.prod.website-files.com/6961d185cb919d4c701e9c24/6961f5c51c7325da51ef2f9f_Group%206.svg";
const dividerTextureUrl =
  "https://cdn.prod.website-files.com/6961d185cb919d4c701e9c24/69630552b7b6bb94e9f5f655_section%20(1).png";
const footerShapeUrl =
  "https://cdn.prod.website-files.com/6961d185cb919d4c701e9c24/696da40d2658c560d340afab_Group%2020.png";

const SNAPSHOT_FILES = {
  metadata: "metadata.json",
  overview: "overview.json",
  salaryMetrics: "salary_metrics.json",
  topSkills: "top_skills.json",
  skillPairs: "skill_pairs.json",
  cityDistribution: "distributions_city.json",
  cantonDistribution: "distributions_canton.json",
  roleDistribution: "distributions_role_category.json",
  seniorityDistribution: "distributions_seniority.json",
  workModeDistribution: "distributions_work_mode.json",
};

function App() {
  const [state, setState] = useState({
    status: "loading",
    data: null,
    error: null,
  });
  const [salaryBreakdown, setSalaryBreakdown] = useState("role_category");
  const [showAllSalaryGroups, setShowAllSalaryGroups] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadSnapshots() {
      try {
        const entries = await Promise.all(
          Object.entries(SNAPSHOT_FILES).map(async ([key, fileName]) => [
            key,
            await fetchSnapshot(fileName),
          ]),
        );

        if (!cancelled) {
          setState({
            status: "ready",
            data: Object.fromEntries(entries),
            error: null,
          });
        }
      } catch (error) {
        if (!cancelled) {
          setState({
            status: "error",
            data: null,
            error:
              error instanceof Error
                ? error.message
                : "Failed to load public statistics snapshots.",
          });
        }
      }
    }

    loadSnapshots();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return (
      <StatusScreen
        title="Loading public snapshots"
        message="Fetching Swiss IT market statistics from generated JSON exports."
      />
    );
  }

  if (state.status === "error" || !state.data) {
    return (
      <StatusScreen
        title="Snapshot data unavailable"
        message={state.error ?? "The public snapshots could not be loaded."}
      />
    );
  }

  const {
    metadata,
    overview,
    salaryMetrics,
    topSkills,
    skillPairs,
    cityDistribution,
    cantonDistribution,
    roleDistribution,
    seniorityDistribution,
    workModeDistribution,
  } = state.data;

  const overviewMetrics = overview.metrics ?? {};
  const salarySummary = salaryMetrics.summary ?? {};
  const lastUpdated = metadata.generated_at ?? overview.generated_at ?? null;
  const topSkillsItems = selectTopItems(topSkills.overall ?? [], 8);
  const programmingLanguages = topSkills.programming_languages ?? {};
  const programmingLanguageSummary = programmingLanguages.summary ?? {};
  const topProgrammingLanguages = selectTopItems(
    (programmingLanguages.items ?? []).filter(
      (item) => item.programming_language !== "dotnet",
    ),
    8,
  );
  const frameworksLibraries = topSkills.frameworks_libraries ?? {};
  const frameworksSummary = frameworksLibraries.summary ?? {};
  const topFrameworksLibraries = selectTopItems(frameworksLibraries.items ?? [], 8);
  const topPairs = selectTopItems(skillPairs.items ?? [], 4);
  const cityItems = selectTopItems(filterUnknown(cityDistribution.items ?? []), 6);
  const cantonItems = selectTopItems(filterUnknown(cantonDistribution.items ?? []), 6);
  const roleItems = selectTopItems(filterUnknown(roleDistribution.items ?? []), 6);
  const seniorityItems = selectTopItems(filterUnknown(seniorityDistribution.items ?? []), 5);
  const workModeItems = selectTopItems(filterUnknown(workModeDistribution.items ?? []), 4);
  const salaryRoleGroups = (salaryMetrics.by_role_category ?? []).filter(
    (item) => item.role_category && item.role_category !== "Unknown",
  );
  const salarySeniorityGroups = (salaryMetrics.by_seniority ?? []).filter(
    (item) => item.seniority && item.seniority !== "Unknown",
  );
  const salaryRoleItems = showAllSalaryGroups
    ? salaryRoleGroups
    : selectTopItems(salaryRoleGroups, 6);
  const salarySeniorityItems = showAllSalaryGroups
    ? salarySeniorityGroups
    : selectTopItems(salarySeniorityGroups, 6);
  const salaryChartConfig =
    salaryBreakdown === "seniority"
      ? {
          title: "Seniority ranked by average salary",
          description: "Seniority levels with normalized CHF yearly salary ranges.",
          items: salarySeniorityItems,
          groupKey: "seniority",
        }
      : {
          title: "Roles ranked by average salary",
          description: "Role categories with normalized CHF yearly salary ranges.",
          items: salaryRoleItems,
          groupKey: "role_category",
        };
  const topRoleGroups = selectTopItems(
    (topSkills.by_role_category ?? []).filter((group) => group.group !== "Unknown"),
    3,
  );

  return (
    <main className="cy-app">
      <section className="cy-section cy-hero-section" id="overview">
        <div className="cy-container">
          <div className="cy-hero-shell cy-grid">
            <div className="cy-hero-accent-line" />
            <div className="cy-hero-grid">
              <div className="cy-hero-copy">
                <SectionEyebrow label="vivalabit" />
                <img src={flagUrl} alt="" className="cy-hero-copy-flag" />
                <h1 className="cy-heading cy-hero-title">
                  <span className="cy-hero-title-accent">Swiss</span> IT jobs analytics
                </h1>
                <div className="cy-button-row">
                </div>
              </div>

              <div className="cy-hero-visual">
                <div className="cy-hero-frame">
                  <div className="cy-hero-glow" />
                  <img src={heroDotsUrl} alt="" className="cy-hero-dots" />
                  <img src={heroCornerTopLeft} alt="" className="cy-corner cy-corner-top-left" />
                  <img src={heroCornerTopRight} alt="" className="cy-corner cy-corner-top-right" />
                  <img
                    src={heroCornerBottomLeft}
                    alt=""
                    className="cy-corner cy-corner-bottom-left"
                  />
                  <img
                    src={heroCornerBottomRight}
                    alt=""
                    className="cy-corner cy-corner-bottom-right"
                  />

                  <div className="cy-hero-dashboard">
                    <div className="cy-hero-stat-grid">
                      <div className="cy-card cy-hero-stat-card">
                        <p className="cy-hero-stat-label">Vacancies</p>
                        <p className="cy-hero-stat-value cy-hero-stat-value-accent">
                          {formatInteger(overviewMetrics.total_vacancies)}
                        </p>
                      </div>
                      <div className="cy-card cy-hero-stat-card">
                        <p className="cy-hero-stat-label">Snapshot Date</p>
                        <p className="cy-hero-stat-value cy-hero-stat-value-accent">
                          {formatShortDate(lastUpdated)}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="cy-section cy-surface-section">
        <div className="cy-container">
          <div className="cy-metrics-grid cy-metrics-grid-compact">
            <MetricCard
              value={formatInteger(overviewMetrics.total_vacancies)}
              description="Total vacancies in the current public export."
            />
            <MetricCard
              value={formatInteger(overviewMetrics.total_companies)}
              description="Distinct employers represented in the dataset."
            />
            <MetricCard
              value={formatDecimal(overviewMetrics.average_vacancies_per_company)}
              description="Average vacancy volume per company."
            />
            <MetricCard
              value={formatShortDate(lastUpdated)}
              description="Latest snapshot generation date in Zurich time."
            />
          </div>
        </div>
      </section>

      <SectionDivider />

      <section className="cy-section" id="charts">
        <div className="cy-container">
          <div className="cy-section-intro cy-section-intro-compact">
            <h2 className="cy-heading cy-section-title">
              Analysis <span className="cy-hero-title-accent">dashboard</span>
            </h2>
          </div>

          <div className="cy-dashboard-grid">
            <article className="cy-card cy-dashboard-panel">
              <div className="cy-data-panel-head">
                <h3>Role category share</h3>
              </div>
              <HorizontalBarChart
                items={roleItems}
                labelKey="label"
                valueKey="vacancy_count"
                shareKey="share"
              />
            </article>

            <article className="cy-card cy-dashboard-panel">
              <div className="cy-data-panel-head">
                <h3>Leading cantons</h3>
              </div>
              <HorizontalBarChart
                items={cantonItems}
                labelKey="label"
                valueKey="vacancy_count"
                shareKey="share"
              />
            </article>

            <article className="cy-card cy-dashboard-panel">
              <div className="cy-data-panel-head">
                <h3>Work mode distribution</h3>
              </div>
              <SegmentChart items={workModeItems} />
            </article>

            <article className="cy-card cy-dashboard-panel">
              <div className="cy-data-panel-head">
                <h3>Seniority mix</h3>
              </div>
              <SegmentChart items={seniorityItems} />
            </article>

            <article className="cy-card cy-dashboard-panel">
              <div className="cy-data-panel-head">
                <h3>Top cities</h3>
              </div>
              <HorizontalBarChart
                items={cityItems}
                labelKey="label"
                valueKey="vacancy_count"
                shareKey="share"
              />
            </article>
          </div>
        </div>
      </section>

      <SectionDivider />

      <section className="cy-section" id="salary">
        <div className="cy-container">
          <div className="cy-section-intro cy-section-intro-compact">
            <h2 className="cy-heading cy-section-title">
              Salary <span className="cy-hero-title-accent">metrics</span>
            </h2>
          </div>

          <div className="cy-salary-layout">
            <article className="cy-card cy-data-panel cy-salary-summary-panel">
              <div className="cy-data-panel-head">
                <h3>Compensation snapshot</h3>
                <p className="cy-copy">
                  Comparable CHF salaries normalized to yearly values.
                </p>
              </div>

              <div className="cy-salary-toggle" aria-label="Salary breakdown">
                <button
                  type="button"
                  className={salaryBreakdown === "role_category" ? "is-active" : ""}
                  onClick={() => setSalaryBreakdown("role_category")}
                >
                  Roles
                </button>
                <button
                  type="button"
                  className={salaryBreakdown === "seniority" ? "is-active" : ""}
                  onClick={() => setSalaryBreakdown("seniority")}
                >
                  Seniority
                </button>
              </div>

              <div className="cy-salary-stat-grid">
                <SalaryStat
                  value={formatCurrency(salarySummary.average_salary)}
                  label="Average yearly"
                />
                <SalaryStat
                  value={formatCurrency(salarySummary.median_salary)}
                  label="Median yearly"
                />
                <SalaryStat
                  value={formatPercent(salarySummary.salary_coverage)}
                  label="Salary coverage"
                />
                <SalaryStat value={formatInteger(salarySummary.salary_count)} label="Records" />
              </div>

              <button
                type="button"
                className="cy-salary-more-button"
                onClick={() => setShowAllSalaryGroups((value) => !value)}
              >
                {showAllSalaryGroups ? "Less" : "More"}
              </button>
            </article>

            <article className="cy-card cy-data-panel cy-salary-chart-panel">
              <div className="cy-data-panel-head">
                <h3>{salaryChartConfig.title}</h3>
                <p className="cy-copy">{salaryChartConfig.description}</p>
              </div>
              <SalaryRankingChart
                items={salaryChartConfig.items}
                summary={salarySummary}
                groupKey={salaryChartConfig.groupKey}
              />
            </article>
          </div>
        </div>
      </section>

      <SectionDivider />

      <section className="cy-section" id="skills">
        <div className="cy-container">
          <div className="cy-section-intro cy-section-intro-compact">
            <h2 className="cy-heading cy-section-title">
              Top <span className="cy-hero-title-accent">skills</span> and{" "}
              <span className="cy-hero-title-accent">pairings</span>
            </h2>
          </div>

          <div className="cy-data-grid">
            <article className="cy-card cy-data-panel">
              <div className="cy-data-panel-head">
                <h3>Top overall skills</h3>
                <p className="cy-copy">Ranked by vacancy frequency.</p>
              </div>
              <div className="cy-table-shell">
                <table className="cy-data-table">
                  <thead>
                    <tr>
                      <th>Skill</th>
                      <th>Vacancies</th>
                      <th>Share</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topSkillsItems.map((item) => (
                      <tr key={item.skill}>
                        <td>{prettifyLabel(item.skill)}</td>
                        <td>{formatInteger(item.vacancy_count)}</td>
                        <td>{formatPercent(item.share)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>

            <article className="cy-card cy-data-panel">
              <div className="cy-data-panel-head">
                <h3>Frequent pairings</h3>
                <p className="cy-copy">Technologies that often appear together.</p>
              </div>
              <div className="cy-pair-list">
                {topPairs.map((pair) => (
                  <div key={`${pair.skill_1}-${pair.skill_2}`} className="cy-pair-item">
                    <div>
                      <strong>
                        {prettifyLabel(pair.skill_1)} + {prettifyLabel(pair.skill_2)}
                      </strong>
                      <p className="cy-copy">
                        {formatInteger(pair.vacancy_count)} shared vacancies
                      </p>
                    </div>
                    <div className="cy-pair-meter">
                      <div
                        className="cy-pair-meter-fill"
                        style={{
                          width: `${Math.max(
                            (pair.vacancy_count / (topPairs[0]?.vacancy_count || 1)) * 100,
                            10,
                          )}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>

              <div className="cy-role-highlight-grid">
                {topRoleGroups.map((group) => (
                  <div key={group.group} className="cy-role-highlight-card">
                    <p className="cy-kicker">{prettifyLabel(group.group)}</p>
                    <div className="cy-chip-list">
                      {selectTopItems(group.items ?? [], 4).map((item) => (
                        <span key={`${group.group}-${item.skill}`} className="cy-chip">
                          {prettifyLabel(item.skill)} · {formatPercent(item.share_within_group)}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </article>
          </div>

          <article className="cy-card cy-data-panel cy-programming-language-panel">
            <div className="cy-data-panel-head">
              <h3>Top programming languages</h3>
              <p className="cy-copy">Language mentions extracted from the current vacancy snapshot.</p>
            </div>

            <div className="cy-summary-chip-row">
              <span className="cy-chip">
                Coverage · {formatPercent(programmingLanguageSummary.vacancy_coverage)}
              </span>
              <span className="cy-chip">
                Vacancies · {formatInteger(programmingLanguageSummary.vacancies_with_items)}
              </span>
              <span className="cy-chip">
                Distinct languages · {formatInteger(programmingLanguageSummary.distinct_items)}
              </span>
            </div>

            <div className="cy-table-shell">
              <table className="cy-data-table">
                <thead>
                  <tr>
                    <th>Language</th>
                    <th>Vacancies</th>
                    <th>Share</th>
                  </tr>
                </thead>
                <tbody>
                  {topProgrammingLanguages.map((item) => (
                    <tr key={item.programming_language}>
                      <td>{prettifyLabel(item.programming_language)}</td>
                      <td>{formatInteger(item.vacancy_count)}</td>
                      <td>{formatPercent(item.share)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>

          <article className="cy-card cy-data-panel cy-programming-language-panel">
            <div className="cy-data-panel-head">
              <h3>Top frameworks & libraries</h3>
              <p className="cy-copy">Framework and library mentions extracted from the current vacancy snapshot.</p>
            </div>

            <div className="cy-summary-chip-row">
              <span className="cy-chip">
                Coverage · {formatPercent(frameworksSummary.vacancy_coverage)}
              </span>
              <span className="cy-chip">
                Vacancies · {formatInteger(frameworksSummary.vacancies_with_items)}
              </span>
              <span className="cy-chip">
                Distinct items · {formatInteger(frameworksSummary.distinct_items)}
              </span>
            </div>

            <div className="cy-table-shell">
              <table className="cy-data-table">
                <thead>
                  <tr>
                    <th>Framework / Library</th>
                    <th>Vacancies</th>
                    <th>Share</th>
                  </tr>
                </thead>
                <tbody>
                  {topFrameworksLibraries.map((item) => (
                    <tr key={item.framework_library}>
                      <td>{prettifyLabel(item.framework_library)}</td>
                      <td>{formatInteger(item.vacancy_count)}</td>
                      <td>{formatPercent(item.share)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </div>
      </section>

      <SectionDivider />

      <section className="cy-section" id="metadata">
        <div className="cy-container">
        </div>
      </section>

      <footer className="cy-footer">
        <div className="cy-section">
          <div className="cy-container cy-footer-shell cy-footer-shell-compact">
            <img src={footerShapeUrl} alt="" className="cy-footer-shape" />
            <div className="cy-footer-bottom cy-footer-bottom-compact">
              <p>2026</p>
              <p>
                vivalabit
              </p>
            </div>
          </div>
        </div>
      </footer>
    </main>
  );
}

function StatusScreen({ title, message }) {
  return (
    <main className="cy-app">
      <section className="cy-section cy-hero-section">
        <div className="cy-container">
          <div className="cy-hero-shell cy-grid">
            <div className="cy-hero-grid">
              <div className="cy-hero-copy">
                <SectionEyebrow label="Swiss IT Jobs" />
                <h1 className="cy-heading cy-hero-title">{title}</h1>
                <p className="cy-copy cy-hero-text">{message}</p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

function PrimaryButton({ children, href, variant = "solid" }) {
  return (
    <a
      href={href}
      className={`cy-button ${variant === "outline" ? "cy-button-outline" : "cy-button-solid"}`}
    >
      {children}
    </a>
  );
}

function SectionEyebrow({ label }) {
  return (
    <div className="cy-eyebrow">
      <img src={dotUrl} alt="" width="18" height="18" />
      <p>{label}</p>
    </div>
  );
}

function SectionDivider() {
  return (
    <div className="cy-divider">
      <img src={dividerTextureUrl} alt="" className="cy-divider-texture" />
    </div>
  );
}

function MetricCard({ value, description }) {
  return (
    <article className="cy-card cy-metric-card">
      <div className="cy-metric-value">{value}</div>
      <p className="cy-copy">{description}</p>
    </article>
  );
}

function SalaryStat({ value, label }) {
  return (
    <div className="cy-salary-stat">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function HorizontalBarChart({ items, labelKey, valueKey, shareKey }) {
  const maxValue = Math.max(...items.map((item) => item[valueKey] ?? 0), 1);

  return (
    <div className="cy-bar-list">
      {items.map((item) => (
        <div key={item.key ?? item[labelKey]} className="cy-bar-list-row">
          <div className="cy-bar-list-head">
            <span>{prettifyLabel(item[labelKey])}</span>
            <strong>
              {formatInteger(item[valueKey])} · {formatPercent(item[shareKey])}
            </strong>
          </div>
          <div className="cy-bar-list-track">
            <div
              className="cy-bar-list-fill"
              style={{ width: `${Math.max((item[valueKey] / maxValue) * 100, 8)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function SegmentChart({ items }) {
  return (
    <div className="cy-segment-chart">
      <div className="cy-segment-bar">
        {items.map((item, index) => (
          <div
            key={item.key}
            className={`cy-segment-slice cy-segment-slice-${index + 1}`}
            style={{ width: `${Math.max(item.share * 100, 6)}%` }}
            title={`${prettifyLabel(item.label)}: ${formatPercent(item.share)}`}
          />
        ))}
      </div>
      <div className="cy-segment-legend">
        {items.map((item, index) => (
          <div key={item.key} className="cy-segment-legend-row">
            <span className={`cy-segment-dot cy-segment-slice-${index + 1}`} />
            <span>{prettifyLabel(item.label)}</span>
            <strong>
              {formatInteger(item.vacancy_count)} · {formatPercent(item.share)}
            </strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function SalaryRankingChart({ items, summary, groupKey }) {
  const maxValue = Math.max(
    ...items.map((item) => item.average_salary ?? 0),
    summary.median_salary ?? 0,
    1,
  );
  const referenceValues = [
    { label: "Median", value: summary.median_salary },
  ].filter((item) => typeof item.value === "number");
  const lastIndex = Math.max(items.length - 1, 1);

  if (!items.length) {
    return <p className="cy-copy cy-empty-state">No comparable salary metrics available.</p>;
  }

  return (
    <div className="cy-salary-chart">
      <div className="cy-salary-reference-layer" aria-hidden="true">
        <div className="cy-salary-reference-track">
          {referenceValues.map((reference) => (
            <div
              key={reference.label}
              className="cy-salary-reference"
              style={{ left: `${Math.min((reference.value / maxValue) * 100, 100)}%` }}
            >
              <span>
                {reference.label} · {formatSalaryShort(reference.value)}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="cy-salary-row-list">
        {items.map((item, index) => (
          <div key={item[groupKey]} className="cy-salary-row">
            <div className="cy-salary-role">
              <strong>{prettifyLabel(item[groupKey])}</strong>
              <span>{formatInteger(item.salary_count)} salaries</span>
            </div>
            <div className="cy-salary-bar-cell">
              <div className="cy-salary-track">
                <div
                  className="cy-salary-fill"
                  style={{
                    width: `${Math.max((item.average_salary / maxValue) * 100, 8)}%`,
                    backgroundColor: getSalaryBarColor(index / lastIndex),
                  }}
                />
              </div>
            </div>
            <span className="cy-salary-value">{formatCurrency(item.average_salary)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

async function fetchSnapshot(fileName) {
  const response = await fetch(`${import.meta.env.BASE_URL}data/${fileName}`);
  if (!response.ok) {
    throw new Error(`Failed to load ${fileName}: ${response.status}`);
  }
  return response.json();
}

function filterUnknown(items) {
  return items.filter((item) => item?.label !== "Unknown" && item?.key !== "Unknown");
}

function selectTopItems(items, limit) {
  return [...items].slice(0, limit);
}

function formatInteger(value) {
  if (typeof value !== "number") {
    return "n/a";
  }
  return new Intl.NumberFormat("en-CH", { maximumFractionDigits: 0 }).format(value);
}

function formatDecimal(value) {
  if (typeof value !== "number") {
    return "n/a";
  }
  return new Intl.NumberFormat("en-CH", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatPercent(value) {
  if (typeof value !== "number") {
    return "n/a";
  }
  return `${(value * 100).toFixed(value >= 0.1 ? 1 : 2)}%`;
}

function formatCurrency(value) {
  if (typeof value !== "number") {
    return "n/a";
  }
  return new Intl.NumberFormat("en-CH", {
    style: "currency",
    currency: "CHF",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatSalaryShort(value) {
  if (typeof value !== "number") {
    return "n/a";
  }
  return `CHF ${Math.round(value / 1000)}k`;
}

function getSalaryBarColor(progress) {
  const start = [169, 0, 7];
  const end = [255, 122, 130];
  const clampedProgress = Math.min(Math.max(progress, 0), 1);
  const channel = (index) =>
    Math.round(start[index] + (end[index] - start[index]) * clampedProgress);
  return `rgb(${channel(0)}, ${channel(1)}, ${channel(2)})`;
}

function formatDateTime(value) {
  if (!value) {
    return "n/a";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "n/a";
  }

  return new Intl.DateTimeFormat("en-CH", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Zurich",
  }).format(date);
}

function formatShortDate(value) {
  if (!value) {
    return "n/a";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "n/a";
  }

  return new Intl.DateTimeFormat("en-CH", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "Europe/Zurich",
  }).format(date);
}

function prettifyLabel(value) {
  if (!value) {
    return "n/a";
  }

  const normalizedValue = String(value).normalize("NFC");
  const normalizedKey = normalizedValue.toLocaleLowerCase("en-US");
  const dictionary = {
    ci_cd: "CI/CD",
    qa_testing: "QA Testing",
    ux_ui_design: "UX/UI Design",
    data_ai: "Data / AI",
    devops_cloud_platform: "DevOps / Cloud / Platform",
    software_engineering: "Software Engineering",
    support_operations: "Support / Operations",
    product_project_analysis: "Product / Project / Analysis",
    erp_business_systems: "ERP / Business Systems",
    rest_api: "REST API",
    dotnet: ".NET",
    csharp: "C#",
    sql: "SQL",
    javascript: "JavaScript",
    typescript: "TypeScript",
    nodejs: "Node.js",
    pytorch: "PyTorch",
    zürich: "Zürich",
    genève: "Genève",
  };

  if (dictionary[normalizedKey]) {
    return dictionary[normalizedKey];
  }

  return normalizedValue
    .replace(/_/g, " ")
    .split(/(\s+|-|\/)/)
    .map((part) => {
      if (/^\s+$|^-$|^\/$/.test(part) || part.length === 0) {
        return part;
      }

      const lowerPart = part.toLocaleLowerCase("en-US");
      return lowerPart.charAt(0).toLocaleUpperCase("en-US") + lowerPart.slice(1);
    })
    .join("");
}

export default App;
