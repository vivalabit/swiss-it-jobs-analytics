import { useEffect, useState } from "react";

import dotUrl from "./assets/images/arrow-badge-right.svg";
import flagUrl from "./assets/images/flag.png";
import swissMapUrl from "./assets/images/swiss-map.png";
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
  companyDistribution: "distributions_company.json",
  cityDistribution: "distributions_city.json",
  cantonDistribution: "distributions_canton.json",
  roleDistribution: "distributions_role_category.json",
  seniorityDistribution: "distributions_seniority.json",
  workModeDistribution: "distributions_work_mode.json",
};

const SWISS_MAP = {
  width: 1300,
  height: 1300,
  viewBox: "0 250 1300 800",
  minLon: 5.85,
  maxLon: 10.55,
  minLat: 45.75,
  maxLat: 47.85,
  paddingX: 191,
  paddingY: 358,
};

const MAP_LABEL_OFFSETS = {
  zurich: [10, -18],
  bern: [-10, 22],
  geneva: [-16, 20],
  basel: [12, -14],
  lausanne: [12, 16],
  luzern: [12, 20],
  winterthur: [12, -4],
  zug: [14, 4],
  "st-gallen": [12, -10],
  aarau: [-10, -18],
  baden: [10, -16],
  wallisellen: [10, 18],
};

const CITY_LOCATIONS = [
  cityLocation("zurich", "Zürich", 47.3769, 8.5417, [
    "Zurich",
    "Zuerich",
    "CH Zürich",
    "CH - Zürich",
    "Zürich Seebach",
    "Zürich Flughafen",
    "Zürich Oerlikon",
    "Zurich Headquarter",
    "Zurich ZNLZ",
    "Zurich region",
    "Remote Switzerland City of Zurich Lakeside",
  ]),
  cityLocation("bern", "Bern", 46.9481, 7.4474, ["Berne", "Stadt Bern", "Raum Bern"]),
  cityLocation("geneva", "Genève", 46.2044, 6.1432, [
    "Geneva",
    "Genf",
    "Région Genève",
    "Grand Lancy Geneva",
  ]),
  cityLocation("basel", "Basel", 47.5596, 7.5886, [
    "Basel City",
    "Basel-Stadt",
    "Region Basel-Stadt",
    "Region Basel-Landschaft",
    "Raum Basel",
  ]),
  cityLocation("luzern", "Luzern", 47.0502, 8.3093, [
    "Lucerne",
    "Region Luzern",
    "Luzern-Stadt District",
  ]),
  cityLocation("lausanne", "Lausanne", 46.5197, 6.6323, ["Lausanne und Homeoffice"]),
  cityLocation("winterthur", "Winterthur", 47.5009, 8.7237, ["Region Winterthur"]),
  cityLocation("zug", "Zug", 47.1662, 8.5155, ["Region Zug"]),
  cityLocation("st-gallen", "St. Gallen", 47.4245, 9.3767, [
    "St Gallen",
    "St.Gallen",
    "Sankt Gallen",
    "Region Sankt Gallen",
    "Region St. Gallen",
    "Kanton St. Gallen",
    "Wahlkreis St. Gallen",
  ]),
  cityLocation("aarau", "Aarau", 47.3904, 8.0444),
  cityLocation("baden", "Baden", 47.4733, 8.3083),
  cityLocation("wallisellen", "Wallisellen", 47.414, 8.5922),
  cityLocation("olten", "Olten", 47.3499, 7.9079),
  cityLocation("lenzburg", "Lenzburg", 47.3885, 8.1803),
  cityLocation("frauenfeld", "Frauenfeld", 47.5582, 8.8988),
  cityLocation("baar", "Baar", 47.1963, 8.5267),
  cityLocation("thun", "Thun", 46.758, 7.6279),
  cityLocation("solothurn", "Solothurn", 47.2088, 7.5325, ["Region Solothurn"]),
  cityLocation("herisau", "Herisau", 47.386, 9.2795),
  cityLocation("rotkreuz", "Rotkreuz", 47.1424, 8.4313, ["ROTKREUZ"]),
  cityLocation("sursee", "Sursee", 47.171, 8.111, ["Region Sursee"]),
  cityLocation("spreitenbach", "Spreitenbach", 47.4235, 8.3672),
  cityLocation("schlieren", "Schlieren", 47.3971, 8.4478),
  cityLocation("schaffhausen", "Schaffhausen", 47.6973, 8.6349, ["Region Zürich Schaffhausen"]),
  cityLocation("chur", "Chur", 46.8508, 9.532),
  cityLocation("moosseedorf", "Moosseedorf", 47.019, 7.483),
  cityLocation("reinach", "Reinach", 47.493, 7.589, ["Reinach CH-BL"]),
  cityLocation("allschwil", "Allschwil", 47.5507, 7.5446),
  cityLocation("fribourg", "Fribourg", 46.8065, 7.1619, ["Région Fribourg"]),
  cityLocation("kriens", "Kriens", 47.034, 8.282),
  cityLocation("steinhausen", "Steinhausen", 47.195, 8.4864),
  cityLocation("opfikon", "Opfikon", 47.431, 8.5628, ["Glattbrugg", "Glattpark"]),
  cityLocation("pully", "Pully", 46.5101, 6.6618),
  cityLocation("schwyz", "Schwyz", 47.0207, 8.6541),
  cityLocation("hinwil", "Hinwil", 47.302, 8.843),
  cityLocation("maegenwil", "Mägenwil", 47.411, 8.228, ["Maegenwil"]),
  cityLocation("biel", "Biel/Bienne", 47.1368, 7.2472, ["Biel", "Bienne", "Biel Bienne"]),
  cityLocation("volketswil", "Volketswil", 47.3902, 8.6907),
  cityLocation("cham", "Cham", 47.183, 8.464),
  cityLocation("emmen", "Emmen", 47.078, 8.298),
  cityLocation("horgen", "Horgen", 47.259, 8.6003),
  cityLocation("neuchatel", "Neuchâtel", 46.9918, 6.931, ["Neuchatel", "CHE Neuchatel"]),
  cityLocation("urdorf", "Urdorf", 47.389, 8.424),
  cityLocation("bussnang", "Bussnang", 47.557, 9.087),
  cityLocation("buelach", "Bülach", 47.517, 8.541, ["Bulach"]),
  cityLocation("dietikon", "Dietikon", 47.405, 8.403),
  cityLocation("duebendorf", "Dübendorf", 47.397, 8.618, ["Dubendorf"]),
  cityLocation("daellikon", "Dällikon", 47.439, 8.438, ["Daellikon"]),
  cityLocation("yverdon", "Yverdon-les-Bains", 46.7785, 6.6412, ["Yverdon"]),
  cityLocation("altishofen", "Altishofen", 47.199, 7.968),
  cityLocation("bioggio", "Bioggio", 46.014, 8.911),
  cityLocation("lugano", "Lugano", 46.004, 8.951),
  cityLocation("rothenburg", "Rothenburg", 47.092, 8.27),
  cityLocation("bonaduz", "Bonaduz", 46.812, 9.397),
  cityLocation("eschlikon", "Eschlikon", 47.463, 8.963),
  cityLocation("kloten", "Kloten", 47.452, 8.584),
  cityLocation("langenthal", "Langenthal", 47.214, 7.785, ["Region Langenthal"]),
  cityLocation("pfaeffikon", "Pfäffikon", 47.202, 8.778, ["Pfaeffikon"]),
  cityLocation("rapperswil-jona", "Rapperswil-Jona", 47.226, 8.82, [
    "Rapperswil",
    "Rapperswi-Jona",
    "Jona",
  ]),
  cityLocation("ostermundigen", "Ostermundigen", 46.956, 7.484),
  cityLocation("stabio", "Stabio", 45.848, 8.935),
  cityLocation("wil", "Wil", 47.462, 9.047, ["Region Wil Ostschweiz"]),
  cityLocation("wohlen", "Wohlen", 47.352, 8.277),
  cityLocation("zofingen", "Zofingen", 47.287, 7.945),
  cityLocation("liestal", "Liestal", 47.484, 7.733),
  cityLocation("burgdorf", "Burgdorf", 47.059, 7.627),
  cityLocation("coppet", "Coppet", 46.316, 6.192),
  cityLocation("sion", "Sion", 46.233, 7.3606),
  cityLocation("staefa", "Stäfa", 47.242, 8.723, ["Staefa"]),
  cityLocation("adliswil", "Adliswil", 47.312, 8.525),
  cityLocation("bellevue", "Bellevue", 46.257, 6.155),
  cityLocation("chiasso", "Chiasso", 45.833, 9.031),
  cityLocation("ecublens", "Ecublens", 46.529, 6.561),
  cityLocation("landquart", "Landquart", 46.968, 9.564),
  cityLocation("muhen", "Muhen", 47.335, 8.055),
  cityLocation("wetzikon", "Wetzikon", 47.326, 8.797),
  cityLocation("aadorf", "Aadorf", 47.493, 8.9),
  cityLocation("altendorf", "Altendorf", 47.192, 8.83),
  cityLocation("bottighofen", "Bottighofen", 47.636, 9.209),
  cityLocation("bulle", "Bulle", 46.618, 7.057),
  cityLocation("heerbrugg", "Heerbrugg", 47.4105, 9.626),
  cityLocation("kemptthal", "Kemptthal", 47.4505, 8.705),
  cityLocation("laufenburg", "Laufenburg", 47.56, 8.061),
  cityLocation("nottwil", "Nottwil", 47.135, 8.137),
  cityLocation("prilly", "Prilly", 46.536, 6.596),
  cityLocation("ruswil", "Ruswil", 47.085, 8.126),
  cityLocation("st-margrethen", "St. Margrethen", 47.451, 9.637),
  cityLocation("turgi", "Turgi", 47.493, 8.252),
  cityLocation("weinfelden", "Weinfelden", 47.566, 9.108),
  cityLocation("bubikon", "Bubikon", 47.267, 8.817),
  cityLocation("buchs-sg", "Buchs SG", 47.167, 9.477, ["Buchs St. Gallen"]),
  cityLocation("domat-ems", "Domat/Ems", 46.834, 9.451),
  cityLocation("fehraltorf", "Fehraltorf", 47.388, 8.751),
  cityLocation("muttenz", "Muttenz", 47.526, 7.645),
  cityLocation("paudex", "Paudex", 46.505, 6.669),
  cityLocation("rheinfelden", "Rheinfelden", 47.554, 7.794),
  cityLocation("root", "Root", 47.114, 8.39),
  cityLocation("stans", "Stans", 46.958, 8.365),
  cityLocation("suhr", "Suhr", 47.374, 8.078),
  cityLocation("wuerenlingen", "Würenlingen", 47.533, 8.256, ["Wurenlingen"]),
  cityLocation("zollikofen", "Zollikofen", 46.999, 7.459, ["Hauptsitz Zollikofen"]),
  cityLocation("affoltern-am-albis", "Affoltern am Albis", 47.277, 8.447),
  cityLocation("brugg", "Brugg", 47.486, 8.209),
  cityLocation("davos", "Davos", 46.802, 9.838, ["Davos Platz"]),
  cityLocation("dietlikon", "Dietlikon", 47.421, 8.619),
  cityLocation("dotzigen", "Dotzigen", 47.121, 7.342),
  cityLocation("ebikon", "Ebikon", 47.08, 8.342),
  cityLocation("fully", "Fully", 46.138, 7.116),
  cityLocation("lyss", "Lyss", 47.074, 7.306),
  cityLocation("muri-ag", "Muri", 47.276, 8.339),
  cityLocation("muri-be", "Muri b. Bern", 46.931, 7.486),
  cityLocation("nidau", "Nidau", 47.126, 7.24),
  cityLocation("oberrueti", "Oberrüti", 47.167, 8.393, ["Oberruti"]),
  cityLocation("port", "Port", 47.114, 7.253),
  cityLocation("regensdorf", "Regensdorf", 47.435, 8.468),
  cityLocation("schwerzenbach", "Schwerzenbach", 47.382, 8.657),
  cityLocation("seuzach", "Seuzach", 47.535, 8.733),
  cityLocation("sulgen", "Sulgen", 47.539, 9.184),
  cityLocation("teufen", "Teufen", 47.39, 9.386),
  cityLocation("thalwil", "Thalwil", 47.291, 8.564),
  cityLocation("aarburg", "Aarburg", 47.321, 7.905),
  cityLocation("amriswil", "Amriswil", 47.546, 9.295),
  cityLocation("appenzell", "Appenzell", 47.331, 9.409),
  cityLocation("dottikon", "Dottikon", 47.386, 8.24),
  cityLocation("daettwil", "Dättwil", 47.454, 8.295, ["Daettwil"]),
  cityLocation("effretikon", "Effretikon", 47.425, 8.686),
  cityLocation("gland", "Gland", 46.42, 6.27),
  cityLocation("grand-lancy", "Grand-Lancy", 46.184, 6.126),
  cityLocation("grosshoechstetten", "Grosshöchstetten", 46.905, 7.637, [
    "Grosshochstetten",
  ]),
  cityLocation("gruesch", "Grüsch", 46.981, 9.645, ["Gruesch"]),
  cityLocation("haag", "Haag", 47.21, 9.489),
  cityLocation("hochdorf", "Hochdorf", 47.168, 8.291),
  cityLocation("jegenstorf", "Jegenstorf", 47.049, 7.507),
  cityLocation("kreuzlingen", "Kreuzlingen", 47.645, 9.175),
  cityLocation("meilen", "Meilen", 47.269, 8.643),
  cityLocation("meiringen", "Meiringen", 46.727, 8.184),
  cityLocation("meisterschwanden", "Meisterschwanden", 47.294, 8.229),
  cityLocation("oberbueren", "Oberbüren", 47.452, 9.166, ["Oberburen"]),
  cityLocation("renens", "Renens", 46.539, 6.588),
  cityLocation("sissach", "Sissach", 47.464, 7.811),
];

const CITY_LOCATION_BY_KEY = new Map(CITY_LOCATIONS.map((city) => [city.key, city]));
const CITY_ALIAS_LOOKUP = new Map(
  CITY_LOCATIONS.flatMap((city) =>
    [city.label, city.key, ...(city.aliases ?? [])].map((alias) => [
      normalizeCityLabel(alias),
      city.key,
    ]),
  ),
);
const CITY_ALIAS_PATTERNS = [...CITY_ALIAS_LOOKUP.entries()]
  .filter(([alias]) => alias.length >= 3)
  .sort((a, b) => b[0].length - a[0].length);

const STAFFING_AGENCY_COMPANY_NAMES = new Set(
  [
    "Adecco",
    "albedis",
    "Art of Work Personalberatung AG",
    "bruederlinpartner GmbH",
    "Careerplus AG",
    "Consult & Pepper AG",
    "Experis",
    "Experis AG",
    "Freestar-Informatik AG",
    "Hays",
    "Impact Recruitment GmbH",
    "ITech Consult AG",
    "ictjobs (Stellenmarkt)",
    "IQ Plus AG",
    "Job Impuls AG",
    "Manpower",
    "Michael Page",
    "mühlemann IT-personal",
    "myitjob GmbH",
    "myScience",
    "Nemensis AG",
    "Nexus Personal- & Unternehmensberatung AG",
    "ONE Agency GmbH",
    "Page Personnel",
    "persona service GmbH",
    "Prime21",
    "Prime21 AG",
    "Progress Personal AG",
    "Randstad",
    "Randstad (Schweiz) AG",
    "Rocken®",
    "Rockstar Recruiting AG",
    "Summit Recruitment AG",
    "Universal-Job AG",
    "Work Selection",
    "yellowshark",
  ].map(normalizeCompanyName),
);

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
    companyDistribution,
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
  const companyItems = selectTopItems(
    filterStaffingAgencies(filterUnknown(companyDistribution.items ?? [])),
    8,
  );
  const cityItems = selectTopItems(filterUnknown(cityDistribution.items ?? []), 6);
  const cityMapItems = buildSwissCityVacancyPoints(cityDistribution.items ?? []);
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

      <section className="cy-section" id="vacancy-map">
        <div className="cy-container">
          <div className="cy-section-intro cy-section-intro-compact">
            <h2 className="cy-heading cy-section-title">
              Swiss vacancy <span className="cy-hero-title-accent">map</span>
            </h2>
          </div>

          <SwissVacancyMap items={cityMapItems} />
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

            <article className="cy-card cy-dashboard-panel cy-company-panel">
              <div className="cy-data-panel-head">
                <h3>Top direct employers</h3>
                <p className="cy-copy">Recruiting agencies and job boards are excluded.</p>
              </div>
              <HorizontalBarChart
                items={companyItems}
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

function SwissVacancyMap({ items }) {
  const maxValue = Math.max(...items.map((item) => item.vacancy_count), 1);
  const mappedVacancies = items.reduce((sum, item) => sum + item.vacancy_count, 0);
  const markerItems = [...items].sort((a, b) => a.vacancy_count - b.vacancy_count);
  const labelItems = items.slice(0, 12);
  const legendValues = [
    maxValue,
    Math.max(Math.round(maxValue * 0.35), 1),
    Math.max(Math.round(maxValue * 0.08), 1),
  ];

  if (!items.length) {
    return (
      <article className="cy-card cy-map-panel">
        <div className="cy-data-panel-head">
          <h3>Vacancies by Swiss city</h3>
          <p className="cy-copy cy-empty-state">No mappable Swiss city metrics available.</p>
        </div>
      </article>
    );
  }

  return (
    <article className="cy-card cy-map-panel">
      <div className="cy-map-panel-head">
        <div className="cy-data-panel-head">
          <h3>Vacancies by Swiss city</h3>
          <p className="cy-copy">
            Red bubbles are scaled by vacancy count. Darker and larger bubbles represent stronger
            city concentration.
          </p>
        </div>
        <div className="cy-map-summary" aria-label="Mapped vacancy summary">
          <span>{formatInteger(items.length)} cities</span>
          <strong>{formatInteger(Math.round(mappedVacancies))} mapped vacancies</strong>
        </div>
      </div>

      <div className="cy-map-canvas">
        <svg
          className="cy-swiss-map"
          viewBox={SWISS_MAP.viewBox}
          role="img"
          aria-labelledby="swiss-vacancy-map-title swiss-vacancy-map-description"
        >
          <title id="swiss-vacancy-map-title">Swiss IT job vacancies by city</title>
          <desc id="swiss-vacancy-map-description">
            Switzerland outline with red translucent circles over cities. Circle size and opacity
            increase with vacancy count.
          </desc>
          <defs>
            <filter id="mapBubbleShadow" x="-40%" y="-40%" width="180%" height="180%">
              <feDropShadow dx="0" dy="10" stdDeviation="8" floodColor="#e7000b" floodOpacity="0.16" />
            </filter>
          </defs>

          <image
            className="cy-map-base-image"
            href={swissMapUrl}
            x="0"
            y="0"
            width={SWISS_MAP.width}
            height={SWISS_MAP.height}
            preserveAspectRatio="xMidYMid meet"
          />

          <g className="cy-map-markers">
            {markerItems.map((item) => {
              const [x, y] = projectSwissPoint(item.lon, item.lat);
              const radius = getMapBubbleRadius(item.vacancy_count, maxValue);
              const opacity = getMapBubbleOpacity(item.vacancy_count, maxValue);

              return (
                <g key={item.key} transform={`translate(${x} ${y})`}>
                  <circle
                    className="cy-map-bubble"
                    r={radius}
                    fillOpacity={opacity}
                    strokeOpacity={Math.min(opacity + 0.18, 0.86)}
                    filter="url(#mapBubbleShadow)"
                  >
                    <title>
                      {item.label}: {formatInteger(Math.round(item.vacancy_count))} vacancies
                    </title>
                  </circle>
                  <circle className="cy-map-city-dot" r="2.6" />
                </g>
              );
            })}
          </g>

          <g className="cy-map-labels">
            {labelItems.map((item) => {
              const [x, y] = projectSwissPoint(item.lon, item.lat);
              const [dx, dy] = MAP_LABEL_OFFSETS[item.key] ?? [10, -12];

              return (
                <text
                  key={`${item.key}-label`}
                  x={x + dx}
                  y={y + dy}
                  textAnchor={dx < 0 ? "end" : "start"}
                >
                  <tspan className="cy-map-label-name">{item.label}</tspan>
                  <tspan className="cy-map-label-value" x={x + dx} dy="13">
                    {formatInteger(Math.round(item.vacancy_count))}
                  </tspan>
                </text>
              );
            })}
          </g>
        </svg>
      </div>

      <div className="cy-map-legend" aria-label="Bubble size legend">
        {legendValues.map((value) => (
          <div key={value} className="cy-map-legend-item">
            <span
              className="cy-map-legend-bubble"
              style={{
                width: `${getMapBubbleRadius(value, maxValue) * 1.25}px`,
                height: `${getMapBubbleRadius(value, maxValue) * 1.25}px`,
                opacity: getMapBubbleOpacity(value, maxValue),
              }}
            />
            <span>{formatInteger(value)} vacancies</span>
          </div>
        ))}
      </div>
    </article>
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

function cityLocation(key, label, lat, lon, aliases = []) {
  return { key, label, lat, lon, aliases };
}

function buildSwissCityVacancyPoints(items) {
  const totals = new Map();

  for (const item of items) {
    const value = item?.vacancy_count;
    if (typeof value !== "number" || value <= 0) {
      continue;
    }

    const cityKeys = resolveCityKeys(item.label ?? item.key);
    if (!cityKeys.length) {
      continue;
    }

    const weightedValue = value / cityKeys.length;
    for (const cityKey of cityKeys) {
      totals.set(cityKey, (totals.get(cityKey) ?? 0) + weightedValue);
    }
  }

  return [...totals.entries()]
    .map(([key, vacancyCount]) => {
      const city = CITY_LOCATION_BY_KEY.get(key);
      return {
        key,
        label: city.label,
        lat: city.lat,
        lon: city.lon,
        vacancy_count: vacancyCount,
      };
    })
    .filter((item) => item.vacancy_count > 0)
    .sort((a, b) => b.vacancy_count - a.vacancy_count);
}

function resolveCityKeys(value) {
  const normalizedValue = normalizeCityLabel(value);
  if (!normalizedValue || normalizedValue === "unknown" || normalizedValue === "switzerland") {
    return [];
  }

  const directMatch = CITY_ALIAS_LOOKUP.get(normalizedValue);
  if (directMatch) {
    return [directMatch];
  }

  const matches = [];
  for (const [alias, cityKey] of CITY_ALIAS_PATTERNS) {
    if (containsCityAlias(normalizedValue, alias) && !matches.includes(cityKey)) {
      matches.push(cityKey);
    }
  }

  return matches;
}

function containsCityAlias(value, alias) {
  return new RegExp(`(^|\\s)${escapeRegExp(alias)}(\\s|$)`).test(value);
}

function normalizeCityLabel(value) {
  if (!value) {
    return "";
  }

  return String(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/&gt;/gi, " ")
    .replace(/\b(?:che|ch)\b/gi, " ")
    .replace(/[\(\)\[\]\{\}]/g, " ")
    .replace(/[.,:;'"’]/g, " ")
    .replace(/[-_/+]/g, " ")
    .replace(/\b(?:und|oder|or|and|ou|et|im|in|office|homeoffice|remote|region|raum|stadt)\b/gi, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLocaleLowerCase("en-US");
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function projectSwissPoint(lon, lat) {
  const drawableWidth = SWISS_MAP.width - SWISS_MAP.paddingX * 2;
  const drawableHeight = SWISS_MAP.height - SWISS_MAP.paddingY * 2;
  const x =
    SWISS_MAP.paddingX +
    ((lon - SWISS_MAP.minLon) / (SWISS_MAP.maxLon - SWISS_MAP.minLon)) * drawableWidth;
  const y =
    SWISS_MAP.paddingY +
    ((SWISS_MAP.maxLat - lat) / (SWISS_MAP.maxLat - SWISS_MAP.minLat)) * drawableHeight;

  return [x, y];
}

function getMapBubbleRadius(value, maxValue) {
  return 5 + Math.sqrt(value / maxValue) * 42;
}

function getMapBubbleOpacity(value, maxValue) {
  return 0.2 + Math.sqrt(value / maxValue) * 0.52;
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

function filterStaffingAgencies(items) {
  return items.filter((item) => !STAFFING_AGENCY_COMPANY_NAMES.has(normalizeCompanyName(item.label)));
}

function normalizeCompanyName(value) {
  if (!value) {
    return "";
  }

  return String(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/&/g, " and ")
    .replace(/[®™]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLocaleLowerCase("en-US");
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
