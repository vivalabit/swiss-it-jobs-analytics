import { useEffect, useState } from "react";

const SNAPSHOT_FILES = {
  metadata: "metadata.json",
  overview: "overview.json",
  topSkills: "top_skills.json",
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
    return <StatusScreen title="Loading public snapshots" message="Fetching aggregated statistics." />;
  }

  if (state.status === "error" || !state.data) {
    return (
      <StatusScreen
        title="Snapshot data unavailable"
        message={state.error ?? "The public snapshots could not be loaded."}
      />
    );
  }

  const { metadata, overview, topSkills, cantonDistribution, roleDistribution, seniorityDistribution, workModeDistribution } =
    state.data;

  const overviewMetrics = overview.metrics ?? {};
  const lastUpdated = metadata.generated_at ?? overview.generated_at ?? null;
  const cantonItems = selectTopItems(cantonDistribution.items, 8);
  const roleItems = selectTopItems(roleDistribution.items, 8);
  const seniorityItems = seniorityDistribution.items ?? [];
  const workModeItems = workModeDistribution.items ?? [];
  const topSkillsItems = selectTopItems(topSkills.overall, 12);
  const topRoleGroups = selectTopItems(topSkills.by_role_category, 3);

  return (
    <div className="page-shell">
      <div className="page-backdrop" />
      <main className="layout">
        <section className="hero">
          <div className="hero-copy">
            <span className="eyebrow">Swiss IT Jobs</span>
            <h1>Public market statistics from aggregated snapshot data</h1>
            <p className="hero-text">
              This site publishes compact JSON snapshots for open consumption. No SQLite databases,
              raw vacancy descriptions, or backend services are exposed in the web layer.
            </p>
          </div>
          <div className="hero-meta card">
            <MetadataList
              items={[
                ["Last updated", formatDateTime(lastUpdated)],
                ["Snapshot schema", metadata.schema_version ?? "n/a"],
                ["Available CSV exports", metadata.available_csv_files?.length ?? 0],
                ["Generated snapshots", metadata.generated_snapshots?.length ?? 0],
              ]}
            />
          </div>
        </section>

        <section className="stats-grid">
          <StatCard
            label="Vacancies"
            value={formatInteger(overviewMetrics.total_vacancies)}
            note="Across current combined snapshot inputs"
          />
          <StatCard
            label="Companies"
            value={formatInteger(overviewMetrics.total_companies)}
            note="Distinct employers in the aggregated dataset"
          />
          <StatCard
            label="Avg vacancies / company"
            value={formatDecimal(overviewMetrics.average_vacancies_per_company)}
            note="Rounded overview metric from analytics export"
          />
          <StatCard
            label="Top skill coverage"
            value={formatPercent(topSkillsItems[0]?.share)}
            note={topSkillsItems[0] ? `${prettifyLabel(topSkillsItems[0].skill)} appears most often` : "No skill data"}
          />
        </section>

        <section className="content-grid">
          <Panel
            title="Role categories"
            subtitle="Largest vacancy segments in the current public snapshot"
          >
            <HorizontalBars items={roleItems} labelKey="label" valueKey="vacancy_count" shareKey="share" />
          </Panel>

          <Panel
            title="Top cantons"
            subtitle="Geographic concentration by vacancy count"
          >
            <HorizontalBars items={cantonItems} labelKey="label" valueKey="vacancy_count" shareKey="share" />
          </Panel>

          <Panel
            title="Seniority mix"
            subtitle="Current vacancy split by experience level"
          >
            <SegmentList items={seniorityItems} />
          </Panel>

          <Panel
            title="Work mode"
            subtitle="Remote, hybrid, onsite, and unknown distribution"
          >
            <SegmentList items={workModeItems} />
          </Panel>
        </section>

        <section className="content-grid content-grid-wide">
          <Panel
            title="Top skills"
            subtitle="Overall skill frequency from aggregated vacancy snapshots"
          >
            <SkillsTable items={topSkillsItems} />
          </Panel>

          <Panel
            title="Skill leaders by role"
            subtitle="Highest-ranked skills inside the biggest role groups"
          >
            <RoleHighlights groups={topRoleGroups} />
          </Panel>
        </section>

        <section className="content-grid content-grid-wide">
          <Panel
            title="Publishing metadata"
            subtitle="Public-facing build information"
          >
            <MetadataList
              items={[
                ["Source CSV directory", metadata.source_csv_dir ?? "n/a"],
                ["Public data directory", metadata.public_data_dir ?? "n/a"],
                ["Missing CSV files", String(metadata.missing_csv_files?.length ?? 0)],
              ]}
            />
          </Panel>
        </section>
      </main>
    </div>
  );
}

function StatusScreen({ title, message }) {
  return (
    <div className="page-shell">
      <div className="page-backdrop" />
      <main className="layout">
        <section className="hero hero-status">
          <div className="hero-copy">
            <span className="eyebrow">Swiss IT Jobs</span>
            <h1>{title}</h1>
            <p className="hero-text">{message}</p>
          </div>
        </section>
      </main>
    </div>
  );
}

function Panel({ title, subtitle, children }) {
  return (
    <article className="panel card">
      <header className="panel-header">
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
      </header>
      {children}
    </article>
  );
}

function StatCard({ label, value, note }) {
  return (
    <article className="stat-card card">
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
      <p className="stat-note">{note}</p>
    </article>
  );
}

function HorizontalBars({ items, labelKey, valueKey, shareKey }) {
  const maxValue = Math.max(...items.map((item) => Number(item[valueKey] ?? 0)), 1);

  return (
    <div className="bar-list">
      {items.map((item) => {
        const value = Number(item[valueKey] ?? 0);
        const width = `${(value / maxValue) * 100}%`;
        return (
          <div className="bar-row" key={`${item[labelKey]}-${value}`}>
            <div className="bar-label-row">
              <span>{prettifyLabel(item[labelKey])}</span>
              <span>
                {formatInteger(value)} · {formatPercent(item[shareKey])}
              </span>
            </div>
            <div className="bar-track">
              <div className="bar-fill" style={{ width }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function SegmentList({ items }) {
  return (
    <div className="segment-list">
      {items.map((item) => (
        <article className="segment-item" key={`${item.key}-${item.vacancy_count}`}>
          <div>
            <strong>{prettifyLabel(item.label ?? item.key)}</strong>
            <p>{formatInteger(item.vacancy_count)} vacancies</p>
          </div>
          <span>{formatPercent(item.share)}</span>
        </article>
      ))}
    </div>
  );
}

function SkillsTable({ items }) {
  return (
    <div className="table-shell">
      <table>
        <thead>
          <tr>
            <th>Skill</th>
            <th>Vacancies</th>
            <th>Share</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.skill}>
              <td>{prettifyLabel(item.skill)}</td>
              <td>{formatInteger(item.vacancy_count)}</td>
              <td>{formatPercent(item.share)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RoleHighlights({ groups }) {
  return (
    <div className="role-grid">
      {groups.map((group) => (
        <article className="role-card" key={group.group}>
          <h3>{prettifyLabel(group.group)}</h3>
          <ul>
            {group.items.slice(0, 4).map((item) => (
              <li key={`${group.group}-${item.skill}`}>
                <span>{prettifyLabel(item.skill)}</span>
                <span>{formatPercent(item.share_within_group)}</span>
              </li>
            ))}
          </ul>
        </article>
      ))}
    </div>
  );
}

function MetadataList({ items }) {
  return (
    <dl className="metadata-list">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

async function fetchSnapshot(fileName) {
  const response = await fetch(`${import.meta.env.BASE_URL}data/${fileName}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${fileName}: ${response.status}`);
  }
  return response.json();
}

function selectTopItems(items, limit) {
  return Array.isArray(items) ? items.slice(0, limit) : [];
}

function formatInteger(value) {
  return typeof value === "number" ? value.toLocaleString("en-US") : "n/a";
}

function formatDecimal(value) {
  return typeof value === "number" ? value.toFixed(2) : "n/a";
}

function formatPercent(value) {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "n/a";
}

function formatDateTime(value) {
  if (!value) {
    return "n/a";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat("en-CH", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Europe/Zurich",
      }).format(parsed);
}

function prettifyLabel(value) {
  if (!value) {
    return "Unknown";
  }
  return String(value)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export default App;
