import { useEffect, useRef, useState } from "react";

import dotUrl from "./assets/images/arrow-badge-right.svg";
import flagUrl from "./assets/images/flag.png";
import swissMapUrl from "./assets/images/swiss-map.png";
const dividerTextureUrl =
  "https://cdn.prod.website-files.com/6961d185cb919d4c701e9c24/69630552b7b6bb94e9f5f655_section%20(1).png";
const footerShapeUrl =
  "https://cdn.prod.website-files.com/6961d185cb919d4c701e9c24/696da40d2658c560d340afab_Group%2020.png";

const SNAPSHOT_FILES = {
  metadata: "metadata.json",
  overview: "overview.json",
  cityMapDetails: "city_map_details.json",
  educationRequirements: "education_requirements.json",
  experienceRequirements: "experience_requirements.json",
  vacancyTrends: "vacancy_trends.json",
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

const PAGE_SECTION_LINKS = [
  { id: "overview", label: "Overview" },
  { id: "snapshot", label: "Snapshot" },
  { id: "findings", label: "Findings" },
  { id: "vacancy-trends", label: "Trends" },
  { id: "vacancy-map", label: "Map" },
  { id: "charts", label: "Charts" },
  { id: "experience", label: "Experience" },
  { id: "salary", label: "Salary" },
  { id: "skills", label: "Skills" },
  { id: "metadata", label: "Methodology" },
];

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
  bern: [-26, 12],
  geneva: [-16, 20],
  basel: [12, -14],
  lausanne: [12, 16],
  luzern: [16, 34],
  winterthur: [12, -4],
  zug: [16, 18],
  "st-gallen": [12, -10],
  aarau: [-10, -18],
  baden: [10, -16],
  wallisellen: [10, 18],
  appenzell: [16, 4],
  chur: [14, 10],
  fribourg: [-34, 30],
  frauenfeld: [14, -18],
  herisau: [12, -12],
  liestal: [10, -12],
  neuchatel: [-12, -18],
  schaffhausen: [14, -18],
  schwyz: [16, -10],
  sion: [12, 18],
  solothurn: [-12, -18],
  stans: [18, 22],
};

const CANTON_CAPITAL_CITY_KEYS = new Set([
  "aarau",
  "appenzell",
  "basel",
  "bern",
  "chur",
  "frauenfeld",
  "fribourg",
  "geneva",
  "herisau",
  "lausanne",
  "liestal",
  "luzern",
  "neuchatel",
  "schaffhausen",
  "schwyz",
  "sion",
  "solothurn",
  "stans",
  "zug",
  "zurich",
]);
const MAP_CITY_LABEL_MIN_VACANCIES = 35;
const MAP_DETAIL_ROLE_LIMIT = 4;
const MAP_DETAIL_EMPLOYER_LIMIT = 5;

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
const COMPANY_PREVIEW_LIMIT = 8;
const COMPANY_EXPANDED_LIMIT = 24;
const EXPERIENCE_MIN_SAMPLE_SIZE = 10;
const HIDDEN_EXPERIENCE_SENIORITIES = new Set(["intern"]);
const TREND_PERIOD_OPTIONS = [
  { label: "30D", days: 30 },
  { label: "90D", days: 90 },
  { label: "180D", days: 180 },
  { label: "1Y", days: 365 },
  { label: "ALL", days: null },
];
const MONTH_NAMES = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];
const TREND_ROLE_COLORS = [
  "#1f65b7",
  "#cc3b86",
  "#b9852d",
  "#2f806e",
  "#f2df5b",
  "#5b6ee1",
  "#e75a4f",
  "#5f9f45",
];
const SKILL_MATRIX_COLORS = [
  "#3095df",
  "#182a9b",
  "#f25322",
  "#20b9d2",
  "#74158d",
  "#d43ca3",
  "#6d55b3",
  "#5d97df",
  "#f59b5f",
  "#8bd33f",
  "#b748b7",
  "#e82645",
  "#5c16c9",
  "#9d8ee5",
  "#f4ed27",
  "#35c7b6",
  "#20a84f",
  "#ef0b79",
];
const PUBLIC_SNAPSHOT_SOURCES = [
  "LinkedIn",
  "jobs.ch",
  "jobscout24.ch",
  "jobup.ch",
  "swissdevjobs.ch",
];
const SNAPSHOT_SCOPE_ITEMS = [
  "Vacancy volume",
  "Salary benchmarks",
  "Role and seniority mix",
  "City and canton demand",
  "Work mode split",
  "Skill and stack trends",
];
const SNAPSHOT_LIMITATIONS = [
  "Public aggregate snapshot, not a full census of the Swiss market.",
  "Salary benchmarks only use vacancies with explicit pay ranges.",
  "Coverage is limited to vacancies published from 2026 onward.",
  "Some fields are normalized or AI-assisted from posting text and structured metadata.",
];

function App() {
  const [state, setState] = useState({
    status: "loading",
    data: null,
    error: null,
  });
  const [salaryBreakdown, setSalaryBreakdown] = useState("role_category");
  const [showAllSalaryGroups, setShowAllSalaryGroups] = useState(false);
  const [showMoreCompanyItems, setShowMoreCompanyItems] = useState(false);
  const [activeSectionId, setActiveSectionId] = useState(PAGE_SECTION_LINKS[0].id);
  const [selectedMapCityKey, setSelectedMapCityKey] = useState(null);

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

  useEffect(() => {
    if (state.status !== "ready" || !state.data) {
      return undefined;
    }

    const sectionElements = PAGE_SECTION_LINKS.map(({ id }) => document.getElementById(id)).filter(
      Boolean,
    );

    if (!sectionElements.length) {
      return undefined;
    }

    const updateActiveSection = () => {
      let currentSectionId = sectionElements[0].id;

      for (const element of sectionElements) {
        if (element.getBoundingClientRect().top <= 180) {
          currentSectionId = element.id;
        }
      }

      setActiveSectionId(currentSectionId);
    };

    const observer = new IntersectionObserver(
      (entries) => {
        const visibleEntries = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio);

        if (visibleEntries[0]?.target.id) {
          setActiveSectionId(visibleEntries[0].target.id);
        }
      },
      {
        rootMargin: "-18% 0px -58% 0px",
        threshold: [0.2, 0.35, 0.55],
      },
    );

    sectionElements.forEach((element) => observer.observe(element));
    updateActiveSection();
    window.addEventListener("scroll", updateActiveSection, { passive: true });

    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", updateActiveSection);
    };
  }, [state.data, state.status]);

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
    cityMapDetails,
    educationRequirements,
    experienceRequirements,
    vacancyTrends,
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
  const educationSummary = educationRequirements.summary ?? {};
  const experienceSummary = experienceRequirements.summary ?? {};
  const experienceBySeniority = (experienceRequirements.by_seniority ?? [])
    .filter((item) => {
      const seniority = String(item.seniority ?? "").toLocaleLowerCase("en-US");
      return (
        item.seniority &&
        item.seniority !== "Unknown" &&
        !HIDDEN_EXPERIENCE_SENIORITIES.has(seniority)
      );
    })
    .sort(compareExperienceRequirements);
  const salarySummary = salaryMetrics.summary ?? {};
  const topSkillsItems = selectTopItems(topSkills.overall ?? [], 20);
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
  const directCompanyItems = filterStaffingAgencies(
    filterUnknown(companyDistribution.items ?? []),
  );
  const companyItems = selectTopItems(
    directCompanyItems,
    showMoreCompanyItems ? COMPANY_EXPANDED_LIMIT : COMPANY_PREVIEW_LIMIT,
  );
  const hasMoreCompanyItems = directCompanyItems.length > COMPANY_PREVIEW_LIMIT;
  const cityItems = selectTopItems(filterUnknown(cityDistribution.items ?? []), 6);
  const cityMapItems = buildSwissCityVacancyPoints(cityDistribution.items ?? []);
  const cityMapCoverage = buildSwissCityMapCoverage(
    cityDistribution.items ?? [],
    overviewMetrics.total_vacancies,
  );
  const cityMapDetailsByKey = buildSwissCityDetailMap(
    cityMapDetails.items ?? [],
    overviewMetrics.total_vacancies,
  );
  const cityMapOptions = [...cityMapDetailsByKey.values()];
  const selectedCityKey = cityMapDetailsByKey.has(selectedMapCityKey)
    ? selectedMapCityKey
    : cityMapItems[0]?.key ?? null;
  const selectedCityDetails = selectedCityKey ? cityMapDetailsByKey.get(selectedCityKey) ?? null : null;
  const cantonItems = selectTopItems(filterUnknown(cantonDistribution.items ?? []), 6);
  const roleItems = selectTopItems(filterUnknown(roleDistribution.items ?? []), 6);
  const seniorityItems = selectTopItems(filterUnknown(seniorityDistribution.items ?? []), 5);
  const allKnownSeniorityItems = filterUnknown(seniorityDistribution.items ?? []);
  const workModeItems = selectTopItems(filterUnknown(workModeDistribution.items ?? []), 4);
  const availableCsvFiles = metadata.available_csv_files ?? [];
  const missingCsvFiles = metadata.missing_csv_files ?? [];
  const generatedSnapshots = metadata.generated_snapshots ?? [];
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
  const topCity = cityItems[0] ?? null;
  const leadingRole = roleItems[0] ?? null;
  const fastestGrowingRole = getFastestGrowingRole(vacancyTrends);
  const topRoleGroups = selectTopItems(
    (topSkills.by_role_category ?? []).filter((group) => group.group !== "Unknown"),
    3,
  );
  const skillRoleMatrix = buildSkillRoleMatrix(topSkills.by_role_category ?? [], 8, 18);
  const downloadLinks = {
    jsonArchive: `${import.meta.env.BASE_URL}downloads/swiss-it-jobs-json-snapshots.zip`,
    csvArchive: `${import.meta.env.BASE_URL}downloads/swiss-it-jobs-csv-exports.zip`,
  };
  const methodologySteps = [
    "Collect processed vacancy exports from the multi-source analytics pipeline.",
    "Deduplicate and normalize companies, locations, work mode, seniority, and salary fields.",
    "Run AI-assisted vacancy analysis to improve classification accuracy and recover details that rule-based filters can miss.",
    "Convert salary data to comparable yearly CHF ranges before aggregation.",
    "Publish compact JSON snapshots and mirrored CSV extracts for the public dashboard.",
  ];
  const trustLimitations = [...SNAPSHOT_LIMITATIONS];
  const keyFindings = buildKeyFindings({
    topCity,
    leadingRole,
    fastestGrowingRole,
    salarySummary,
  });

  return (
    <main className="cy-app">
      <section className="cy-section cy-hero-section" id="overview">
        <div className="cy-container">
          <div className="cy-hero-shell cy-grid">
            <div className="cy-hero-accent-line" />
            <div className="cy-hero-grid">
              <div className="cy-hero-copy">
                <img src={flagUrl} alt="" className="cy-hero-copy-flag" />
                <h1 className="cy-heading cy-hero-title">
                  <span className="cy-hero-title-accent">Swiss</span> IT Job Market
                </h1>
                <p className="cy-copy cy-hero-text">
                  Track hiring volume, salary benchmarks, and location hotspots from the
                  latest public Swiss IT vacancy data.
                </p>
                <div className="cy-button-row cy-hero-actions">
                  <PrimaryButton href="#vacancy-trends">Explore the dashboard</PrimaryButton>
                  <PrimaryButton href="#methodology" variant="outline">
                    Read methodology
                  </PrimaryButton>
                </div>
                <div className="cy-kpi-grid">
                  <ProductKpiCard
                    label="Vacancies tracked"
                    value={formatInteger(overviewMetrics.total_vacancies)}
                    trendValue={vacancyTrends.summary?.growth_30d ?? null}
                    trendText={
                      vacancyTrends.summary?.published_30d
                        ? `${formatInteger(vacancyTrends.summary.published_30d)} published in 30 days`
                        : "current market coverage"
                    }
                  />
                  <ProductKpiCard
                    label="Median salary"
                    value={formatCurrency(salarySummary.median_salary)}
                    trendValue={salarySummary.salary_coverage}
                    trendText={
                      salarySummary.salary_count
                        ? `${formatInteger(salarySummary.salary_count)} listings with salary data`
                        : "salary benchmark coverage"
                    }
                  />
                  <ProductKpiCard
                    label="Top hiring city"
                    value={prettifyLabel(topCity?.label)}
                    trendValue={topCity?.share}
                    trendText={
                      topCity ? `${formatInteger(topCity.vacancy_count)} active vacancies` : "city demand"
                    }
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="cy-page-shell">
        <div className="cy-page-shell-inner">
          <SectionRail sections={PAGE_SECTION_LINKS} activeSectionId={activeSectionId} />

          <div className="cy-page-content">
            <section className="cy-section cy-trust-section" id="snapshot" aria-labelledby="snapshot-context">
              <div className="cy-container">
                <article className="cy-card cy-trust-panel">
                  <div className="cy-data-panel-head cy-trust-panel-head">
                    <div>
                      <p className="cy-kicker">Snapshot context</p>
                      <h2 id="snapshot-context">What this page is built on</h2>
                    </div>
                    <p className="cy-copy">
                      Quick context on freshness, sample size, coverage, and what the public export
                      does not claim to measure.
                    </p>
                  </div>

                  <div className="cy-trust-grid">
                    <TrustInfoCard
                      label="Sources"
                      title={`${PUBLIC_SNAPSHOT_SOURCES.length} public job boards`}
                    >
                      <div className="cy-chip-list cy-trust-chip-list">
                        {PUBLIC_SNAPSHOT_SOURCES.map((source) => (
                          <span key={source} className="cy-chip">
                            {source}
                          </span>
                        ))}
                      </div>
                      <p className="cy-copy">
                        Deduplicated at vacancy level before the public aggregate is published.
                      </p>
                    </TrustInfoCard>

                    <TrustInfoCard label="Updated" title={formatShortDate(metadata.generated_at)}>
                      <p className="cy-copy">{formatDateTime(metadata.generated_at)}</p>
                    </TrustInfoCard>

                    <TrustInfoCard
                      label="Sample size"
                      title={formatInteger(overviewMetrics.total_vacancies)}
                    >
                      <p className="cy-copy">
                        {formatInteger(overviewMetrics.total_companies)} direct employers after agency
                        filtering.
                      </p>
                    </TrustInfoCard>

                    <TrustInfoCard
                      label="Salary coverage"
                      title={formatPercent(salarySummary.salary_coverage)}
                    >
                      <p className="cy-copy">
                        {formatInteger(salarySummary.salary_count)} listings with normalized CHF yearly
                        salary data.
                      </p>
                    </TrustInfoCard>

                    <TrustInfoCard label="Snapshot includes" title="Core market signals">
                      <div className="cy-chip-list cy-trust-chip-list">
                        {SNAPSHOT_SCOPE_ITEMS.map((item) => (
                          <span key={item} className="cy-chip">
                            {item}
                          </span>
                        ))}
                      </div>
                    </TrustInfoCard>

                    <TrustInfoCard label="Main limitations" title="Read before comparing numbers">
                      <div className="cy-trust-note-list">
                        {trustLimitations.map((item) => (
                          <p key={item} className="cy-copy">
                            {item}
                          </p>
                        ))}
                      </div>
                    </TrustInfoCard>
                  </div>
                </article>
              </div>
            </section>

            <section className="cy-section cy-findings-section" id="findings" aria-labelledby="key-findings">
              <div className="cy-container">
                <article className="cy-card cy-findings-panel">
                  <div className="cy-data-panel-head cy-findings-head">
                    <div>
                      <p className="cy-kicker">Key findings</p>
                      <h2 id="key-findings">What stands out right now</h2>
                    </div>
                  </div>

                  <div className="cy-findings-grid">
                    {keyFindings.map((item) => (
                      <KeyFindingCard
                        key={item.title}
                        label={item.label}
                        title={item.title}
                        description={item.description}
                      />
                    ))}
                  </div>
                </article>
              </div>
            </section>

            <section className="cy-section cy-surface-section">
              <div className="cy-container">
                <div className="cy-metrics-grid cy-product-summary-grid">
                  <MetricCard
                    label="Vacancies tracked"
                    value={formatInteger(overviewMetrics.total_vacancies)}
                    description="Current public export size across the Swiss tech market."
                  />
                  <MetricCard
                    label="Direct employers"
                    value={formatInteger(overviewMetrics.total_companies)}
                    description="Distinct hiring companies after excluding recruiting agencies."
                  />
                  <MetricCard
                    label="Published in 30d"
                    value={formatInteger(vacancyTrends.summary?.published_30d)}
                    description="Latest rolling-month intake of newly published vacancies."
                  />
                  <MetricCard
                    label="Salary coverage"
                    value={formatPercent(salarySummary.salary_coverage)}
                    description={`${formatInteger(salarySummary.salary_count)} vacancies with normalized yearly salary data.`}
                  />
                </div>
              </div>
            </section>

            <SectionDivider />

            <section className="cy-section" id="vacancy-trends">
              <div className="cy-container">
                <VacancyTrendsPanel trends={vacancyTrends} />
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

                <SwissVacancyMap
                  items={cityMapItems}
                  coverage={cityMapCoverage}
                  selectedCityKey={selectedCityKey}
                  selectedCityDetails={selectedCityDetails}
                  cityOptions={cityMapOptions}
                  onSelectCity={setSelectedMapCityKey}
                />
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
                      labelFormatter={formatCantonCode}
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
                    {hasMoreCompanyItems ? (
                      <button
                        type="button"
                        className="cy-data-more-button"
                        onClick={() => setShowMoreCompanyItems((value) => !value)}
                      >
                        {showMoreCompanyItems ? "LESS" : "MORE"}
                      </button>
                    ) : null}
                  </article>
                </div>
              </div>
            </section>

            <SectionDivider />

            <section className="cy-section" id="experience">
              <div className="cy-container">
                <ExperienceRequirementsPanel
                  summary={experienceSummary}
                  bySeniority={experienceBySeniority}
                />
                <SeniorityDistributionPanel items={allKnownSeniorityItems} />
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
                    <p className="cy-copy">
                      Language mentions extracted from the current vacancy snapshot.
                    </p>
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
                    <p className="cy-copy">
                      Framework and library mentions extracted from the current vacancy snapshot.
                    </p>
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

                <article className="cy-card cy-data-panel cy-skill-matrix-panel">
                  <div className="cy-data-panel-head">
                    <h3>Job skills by role</h3>
                    <p className="cy-copy">
                      Skill mix within the leading role categories. Segment width is normalized inside
                      each role.
                    </p>
                  </div>

                  <SkillRoleMatrix matrix={skillRoleMatrix} />
                </article>
              </div>
            </section>

            <SectionDivider />

            <section className="cy-section" id="metadata">
              <div className="cy-container">
                <div id="methodology" className="cy-section-intro cy-section-intro-compact">
                  <h2 className="cy-heading cy-section-title">
                    Read <span className="cy-hero-title-accent">methodology</span>
                  </h2>
                  <p className="cy-copy cy-section-copy">
                    How the public snapshot is assembled, normalized, and published for the
                    dashboard.
                  </p>
                </div>

                <div className="cy-meta-strip">
                  <article className="cy-card cy-data-panel">
                    <div className="cy-data-panel-head">
                      <h3>Pipeline overview</h3>
                      <p className="cy-copy">
                        The dashboard is built from aggregated vacancy exports, AI-assisted vacancy
                        enrichment, and compact public snapshot files.
                      </p>
                    </div>

                    <div className="cy-methodology-step-list">
                      {methodologySteps.map((step, index) => (
                        <div key={step} className="cy-methodology-step-item">
                          <span>{String(index + 1).padStart(2, "0")}</span>
                          <p className="cy-copy">{step}</p>
                        </div>
                      ))}
                    </div>

                    <div className="cy-summary-chip-row">
                      <span className="cy-chip">Source CSV dir · {metadata.source_csv_dir ?? "n/a"}</span>
                      <span className="cy-chip">Public data dir · {metadata.public_data_dir ?? "n/a"}</span>
                      <span className="cy-chip">Schema v{metadata.schema_version ?? "n/a"}</span>
                    </div>
                  </article>

                  <article className="cy-card cy-data-panel">
                    <div className="cy-data-panel-head">
                      <h3>Snapshot coverage</h3>
                      <p className="cy-copy">
                        Current build metadata for the export powering this page.
                      </p>
                    </div>

                    <div className="cy-meta-strip-grid">
                      <MetricCard
                        label="Generated"
                        value={formatShortDate(metadata.generated_at)}
                        description={formatDateTime(metadata.generated_at)}
                      />
                      <MetricCard
                        label="JSON snapshots"
                        value={formatInteger(generatedSnapshots.length)}
                        description="Public files published to the dashboard."
                      />
                      <MetricCard
                        label="CSV inputs"
                        value={formatInteger(availableCsvFiles.length)}
                        description="Analytics exports available for this build."
                      />
                      <MetricCard
                        label="Missing inputs"
                        value={formatInteger(missingCsvFiles.length)}
                        description={
                          missingCsvFiles.length
                            ? missingCsvFiles.join(", ")
                            : "All expected CSV inputs are present."
                        }
                      />
                    </div>

                    <div className="cy-methodology-file-list">
                      {generatedSnapshots.slice(0, 8).map((fileName) => (
                        <span key={fileName} className="cy-chip">
                          {fileName}
                        </span>
                      ))}
                      {generatedSnapshots.length > 8 ? (
                        <span className="cy-chip">+{generatedSnapshots.length - 8} more</span>
                      ) : null}
                    </div>

                    <div className="cy-button-row cy-methodology-downloads">
                      {generatedSnapshots.length ? (
                        <PrimaryButton
                          href={downloadLinks.jsonArchive}
                          download="swiss-it-jobs-json-snapshots.zip"
                        >
                          Download JSON snapshots
                        </PrimaryButton>
                      ) : null}
                      {availableCsvFiles.length ? (
                        <PrimaryButton
                          href={downloadLinks.csvArchive}
                          variant="outline"
                          download="swiss-it-jobs-csv-exports.zip"
                        >
                          Download CSV exports
                        </PrimaryButton>
                      ) : null}
                    </div>
                  </article>
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>

      <footer className="cy-footer">
        <div className="cy-section">
          <div className="cy-container cy-footer-shell cy-footer-shell-compact">
            <img src={footerShapeUrl} alt="" className="cy-footer-shape" />
            <div className="cy-footer-bottom cy-footer-bottom-compact">
              <p>
                <a
                  className="cy-footer-github-link"
                  href="https://github.com/vivalabit/swiss-it-jobs-analytics"
                  target="_blank"
                  rel="noreferrer"
                >
                  <svg
                    aria-hidden="true"
                    viewBox="0 0 16 16"
                    width="16"
                    height="16"
                    className="cy-footer-github-icon"
                  >
                    <path
                      fill="currentColor"
                      d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82A7.65 7.65 0 0 1 8 3.86c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"
                    />
                  </svg>
                  <span>GitHub</span>
                </a>
              </p>
              <p>
                <a href="https://github.com/vivalabit" target="_blank" rel="noreferrer">
                  vivalabit
                </a>
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

function PrimaryButton({ children, href, variant = "solid", download }) {
  return (
    <a
      href={href}
      download={download}
      className={`cy-button ${variant === "outline" ? "cy-button-outline" : "cy-button-solid"}`}
    >
      {children}
    </a>
  );
}

function SectionRail({ sections, activeSectionId }) {
  return (
    <aside className="cy-section-rail" aria-label="Page sections">
      <div className="cy-card cy-section-rail-card">
        <p className="cy-kicker">Navigate</p>
        <nav className="cy-section-rail-nav">
          {sections.map((section, index) => (
            <a
              key={section.id}
              href={`#${section.id}`}
              className={`cy-section-rail-link ${
                activeSectionId === section.id ? "is-active" : ""
              }`}
            >
              <span className="cy-section-rail-index">{String(index + 1).padStart(2, "0")}</span>
              <span>{section.label}</span>
            </a>
          ))}
        </nav>
      </div>
    </aside>
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

function ProductKpiCard({ label, value, trendValue, trendText }) {
  const direction = typeof trendValue === "number" ? (trendValue < 0 ? "down" : "up") : "flat";
  const trendArrow = direction === "down" ? "↓" : direction === "up" ? "↑" : "•";

  return (
    <article className="cy-card cy-kpi-card">
      <p className="cy-kpi-label">{label}</p>
      <div className="cy-kpi-value">{value}</div>
      <div className={`cy-kpi-trend cy-kpi-trend-${direction}`}>
        <span className="cy-kpi-trend-arrow" aria-hidden="true">
          {trendArrow}
        </span>
        <strong>{typeof trendValue === "number" ? formatSignedPercent(trendValue) : "Live"}</strong>
        <span>{trendText}</span>
      </div>
    </article>
  );
}

function MetricCard({ label, value, description }) {
  return (
    <article className="cy-card cy-metric-card">
      <p className="cy-kpi-label">{label}</p>
      <div className="cy-metric-value">{value}</div>
      <p className="cy-copy">{description}</p>
    </article>
  );
}

function TrustInfoCard({ label, title, children }) {
  return (
    <article className="cy-trust-item">
      <p className="cy-kpi-label">{label}</p>
      <h3 className="cy-trust-item-title">{title}</h3>
      <div className="cy-trust-item-body">{children}</div>
    </article>
  );
}

function KeyFindingCard({ label, title, description }) {
  return (
    <article className="cy-finding-card">
      <p className="cy-kpi-label">{label}</p>
      <h3 className="cy-finding-title">{title}</h3>
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

function ExperienceRequirementsPanel({ summary, bySeniority }) {
  const topSeniorityItems = selectTopItems(
    bySeniority.filter((item) => (item.experience_years_count ?? 0) > 0),
    5,
  );
  const maxMentionCount = Math.max(
    ...topSeniorityItems.map((item) => item.experience_years_count ?? 0),
    1,
  );
  const totalMentionCount = Number(summary.experience_years_mentioned_count ?? 0);
  const knownSeniorityMentionCount = topSeniorityItems.reduce(
    (sum, item) => sum + (item.experience_years_count ?? 0),
    0,
  );
  const knownSeniorityMentionShare = totalMentionCount
    ? knownSeniorityMentionCount / totalMentionCount
    : 0;

  return (
    <article className="cy-card cy-data-panel cy-experience-panel">
      <div className="cy-data-panel-head">
        <h3>Experience requirements</h3>
        <p className="cy-copy">
          Explicit years of experience requested in vacancy text, grouped by inferred seniority.
          Averages by seniority require at least {EXPERIENCE_MIN_SAMPLE_SIZE} year mentions.
        </p>
      </div>

      <div className="cy-experience-stat-grid">
        <SalaryStat
          value={formatPercent(knownSeniorityMentionShare)}
          label={`${formatInteger(
            knownSeniorityMentionCount,
          )} year mentions with seniority`}
        />
        <SalaryStat
          value={formatPercent(summary.experience_years_mentioned_share)}
          label={`${formatInteger(
            summary.experience_years_mentioned_count,
          )} mention years of experience`}
        />
        <SalaryStat
          value={formatYears(summary.average_min_experience_years)}
          label="Average minimum requested"
        />
        <SalaryStat
          value={formatYears(summary.median_min_experience_years)}
          label="Median minimum requested"
        />
      </div>

      <div className="cy-experience-layout">
        <div className="cy-experience-bar-list">
          {topSeniorityItems.map((item) => (
            <div key={item.seniority} className="cy-experience-row">
              <div className="cy-experience-row-head">
                <strong>{prettifyLabel(item.seniority)}</strong>
                <span>
                  {formatInteger(item.experience_years_count)} ·{" "}
                  {formatPercent(
                    totalMentionCount
                      ? (item.experience_years_count ?? 0) / totalMentionCount
                      : 0,
                  )}
                </span>
              </div>
              <div className="cy-experience-track">
                <span
                  style={{
                    width: `${Math.max(
                      ((item.experience_years_count ?? 0) / maxMentionCount) * 100,
                      8,
                    )}%`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>

        <div className="cy-table-shell cy-experience-table-shell">
          <div className="cy-data-panel-head cy-experience-table-head">
            <h4>Experience mentions by seniority</h4>
          </div>
          <table className="cy-data-table">
            <thead>
              <tr>
                <th>Seniority</th>
                <th>Avg. min exp.</th>
                <th>Mentions</th>
              </tr>
            </thead>
            <tbody>
              {topSeniorityItems.map((item) => (
                <tr key={`${item.seniority}-experience`}>
                  <td>{prettifyLabel(item.seniority)}</td>
                  <td>
                    {item.experience_years_count >= EXPERIENCE_MIN_SAMPLE_SIZE
                      ? formatYears(item.average_min_experience_years)
                      : "n/a"}
                  </td>
                  <td>{formatInteger(item.experience_years_count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </article>
  );
}

function SeniorityDistributionPanel({ items }) {
  return (
    <article className="cy-card cy-data-panel cy-seniority-distribution-panel">
      <div className="cy-data-panel-head">
        <h3>Seniority distribution</h3>
        <p className="cy-copy">
          Overall inferred seniority mix across vacancies, independent of explicit experience mentions.
        </p>
      </div>

      <div className="cy-table-shell cy-seniority-distribution-table-shell">
        <table className="cy-data-table">
          <thead>
            <tr>
              <th>Seniority</th>
              <th>Vacancies</th>
              <th>Share</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={`${item.key ?? item.label}-distribution`}>
                <td>{prettifyLabel(item.label ?? item.key)}</td>
                <td>{formatInteger(item.vacancy_count)}</td>
                <td>{formatPercent(item.share)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function VacancyTrendsPanel({ trends }) {
  const [periodDays, setPeriodDays] = useState(90);
  const [granularity, setGranularity] = useState("weekly");
  const [selectedCantons, setSelectedCantons] = useState([]);
  const [selectedRoles, setSelectedRoles] = useState([]);
  const allSegments = getTrendSegments(trends, granularity);
  const periodSegments = filterTrendItemsByPeriod(allSegments, periodDays, granularity);
  const locationSegments = filterTrendSegmentsByCantons(periodSegments, selectedCantons);
  const roleOptions = getTopTrendRoles(locationSegments, 8);
  const validSelectedRoles = selectedRoles.filter((role) => roleOptions.includes(role));
  const activeRoles = validSelectedRoles.length ? validSelectedRoles : roleOptions.slice(0, 5);
  const chartSegments = filterTrendSegmentsByRoles(locationSegments, activeRoles);
  const chartData = buildTrendLineChartData(chartSegments, activeRoles, granularity);
  const allLocationSegments = filterTrendSegmentsByCantons(allSegments, selectedCantons);
  const publishedCount = chartSegments.reduce((sum, item) => sum + (item.published_count ?? 0), 0);
  const closedCount = chartSegments.reduce((sum, item) => sum + (item.closed_count ?? 0), 0);
  const growth = calculateSegmentTrendGrowth(
    filterTrendSegmentsByRoles(allLocationSegments, activeRoles),
    periodDays,
    granularity,
  );
  const dailyLocationSegments = filterTrendSegmentsByCantons(
    getTrendSegments(trends, "daily"),
    selectedCantons,
  );
  const seasonality = getTrendRoleSeasonality(
    filterTrendSegmentsByRoles(dailyLocationSegments, activeRoles),
  );
  const strongestMonth = getStrongestSeasonalityMonth(seasonality);
  const weakestMonth = getWeakestSeasonalityMonth(seasonality);
  const cantonOptions = getTrendCantonOptions(
    trends?.segments?.weekly ?? trends?.segments?.daily ?? [],
  );
  const locationLabel = selectedCantons.length
    ? selectedCantons.join(", ")
    : "Switzerland";

  return (
    <article className="cy-card cy-data-panel cy-trend-panel">
      <div className="cy-trend-title-block">
        <p className="cy-kicker">Publication date index</p>
        <h3>Job postings in {locationLabel}</h3>
        <p className="cy-copy">
          Role-category posting trend with canton filters, inferred closures and seasonality.
        </p>
      </div>

      <div className="cy-trend-filter-grid" aria-label="Vacancy trend filters">
        <div className="cy-trend-filter-card">
          <span>Region</span>
          <div className="cy-trend-chip-row">
            <button
              type="button"
              className={selectedCantons.length === 0 ? "is-active" : ""}
              onClick={() => setSelectedCantons([])}
            >
              Switzerland
            </button>
            {cantonOptions.map((canton) => (
              <button
                key={canton}
                type="button"
                className={selectedCantons.includes(canton) ? "is-active" : ""}
                onClick={() => {
                  setSelectedCantons((current) =>
                    current.includes(canton)
                      ? current.filter((item) => item !== canton)
                      : [...current, canton].sort(),
                  );
                }}
              >
                {canton}
              </button>
            ))}
          </div>
        </div>

        <div className="cy-trend-filter-card">
          <span>Professions</span>
          <div className="cy-trend-chip-row">
            {roleOptions.map((role, index) => (
              <button
                key={role}
                type="button"
                className={activeRoles.includes(role) ? "is-active" : ""}
                style={{
                  "--trend-color": getTrendRoleColor(
                    activeRoles.includes(role) ? activeRoles.indexOf(role) : index,
                  ),
                }}
                onClick={() => {
                  setSelectedRoles((current) => {
                    const base = current.length ? current : roleOptions.slice(0, 5);
                    return base.includes(role)
                      ? base.filter((item) => item !== role)
                      : [...base, role];
                  });
                }}
              >
                {prettifyLabel(role)}
              </button>
            ))}
          </div>
        </div>

        <div className="cy-trend-filter-card cy-trend-filter-card-compact">
          <span>Period</span>
          <div className="cy-trend-toggle" aria-label="Period">
            {TREND_PERIOD_OPTIONS.map((option) => (
              <button
                key={option.label}
                type="button"
                className={periodDays === option.days ? "is-active" : ""}
                onClick={() => setPeriodDays(option.days)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="cy-trend-toggle" aria-label="Granularity">
            <button
              type="button"
              className={granularity === "daily" ? "is-active" : ""}
              onClick={() => setGranularity("daily")}
            >
              Days
            </button>
            <button
              type="button"
              className={granularity === "weekly" ? "is-active" : ""}
              onClick={() => setGranularity("weekly")}
            >
              Weeks
            </button>
          </div>
        </div>
      </div>

      <div className="cy-trend-stat-grid">
        <SalaryStat value={formatInteger(publishedCount)} label="Published in selection" />
        <SalaryStat value={formatSignedPercent(growth)} label="Growth vs previous period" />
        <SalaryStat value={formatInteger(closedCount)} label="Closed / disappeared" />
        <SalaryStat
          value={strongestMonth ? MONTH_NAMES[strongestMonth.month - 1] : "n/a"}
          label={
            strongestMonth && weakestMonth
              ? `Seasonality high / low: ${MONTH_NAMES[weakestMonth.month - 1]}`
              : "Seasonality high / low"
          }
        />
      </div>

      <div className="cy-trend-legend" aria-label="Profession legend">
        {chartData.series.map((series, index) => (
          <span key={series.role}>
            <i style={{ background: getTrendRoleColor(index) }} />
            {prettifyLabel(series.role)}
          </span>
        ))}
      </div>

      <div className="cy-trend-line-chart-shell">
        <TrendLineChart chartData={chartData} granularity={granularity} />
      </div>

      <div className="cy-trend-footnote">
        <span>Closed means last seen before the latest crawl.</span>
        <span>Trend uses vacancy publication dates.</span>
      </div>
    </article>
  );
}

function TrendLineChart({ chartData, granularity }) {
  const [hoverIndex, setHoverIndex] = useState(null);
  const width = getTrendChartWidth(chartData.labels.length, granularity);
  const height = 430;
  const margin = {
    top: 24,
    right: granularity === "daily" ? 40 : 24,
    bottom: granularity === "daily" ? 76 : 58,
    left: 66,
  };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const maxValue = Math.max(chartData.maxValue, 1);
  const yTicks = buildYAxisTicks(maxValue);
  const xTickStep = buildTrendXAxisStep(chartData.labels.length, innerWidth, granularity);
  const activeHoverIndex =
    typeof hoverIndex === "number" && chartData.labels[hoverIndex] ? hoverIndex : null;
  const tooltipRows =
    activeHoverIndex === null
      ? []
      : chartData.series.map((series, index) => ({
          role: series.role,
          value: series.values[activeHoverIndex] ?? 0,
          color: getTrendRoleColor(index),
        }));
  const hoverX =
    activeHoverIndex === null
      ? null
      : projectTrendX(activeHoverIndex, chartData.labels.length, innerWidth);
  const tooltipWidth = 330;
  const tooltipHeight = Math.min(54 + tooltipRows.length * 22, height - 26);
  const tooltipX =
    hoverX === null
      ? 0
      : Math.min(
          Math.max(margin.left + hoverX + 16, 8),
          width - tooltipWidth - 8,
        );
  const tooltipY = margin.top + 8;

  if (!chartData.labels.length || !chartData.series.length) {
    return <p className="cy-copy cy-empty-state">No trend data for this selection.</p>;
  }

  function handlePointerMove(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    const relativeX = event.clientX - rect.left;
    const clampedX = Math.min(Math.max(relativeX, 0), rect.width);
    const index = Math.round((clampedX / rect.width) * (chartData.labels.length - 1));
    setHoverIndex(index);
  }

  return (
    <svg className="cy-trend-line-chart" viewBox={`0 0 ${width} ${height}`} role="img">
      <title>Vacancy trend by profession</title>
      <defs>
        <filter id="trendTooltipShadow" x="-10%" y="-10%" width="120%" height="140%">
          <feDropShadow dx="0" dy="10" stdDeviation="10" floodColor="#101828" floodOpacity="0.16" />
        </filter>
      </defs>
      <g transform={`translate(${margin.left} ${margin.top})`}>
        {yTicks.map((tick) => {
          const y = innerHeight - (tick / maxValue) * innerHeight;
          return (
            <g key={tick} className="cy-trend-grid-line">
              <line x1="0" x2={innerWidth} y1={y} y2={y} />
              <text x="-14" y={y + 4} textAnchor="end">
                {formatInteger(tick)}
              </text>
            </g>
          );
        })}

        <line className="cy-trend-axis" x1="0" x2="0" y1="0" y2={innerHeight} />
        <line className="cy-trend-axis" x1="0" x2={innerWidth} y1={innerHeight} y2={innerHeight} />

        {chartData.labels.map((label, index) => {
          if (index % xTickStep !== 0 && index !== chartData.labels.length - 1) {
            return null;
          }
          const x = projectTrendX(index, chartData.labels.length, innerWidth);
          return (
            <text
              key={label}
              className="cy-trend-x-label"
              x={x}
              y={innerHeight + 34}
              textAnchor="end"
              transform={`rotate(-45 ${x} ${innerHeight + 34})`}
            >
              {formatTrendAxisLabel(label, granularity)}
            </text>
          );
        })}

        {chartData.series.map((series, index) => (
          <g key={series.role}>
            <polyline
              className="cy-trend-line"
              fill="none"
              stroke={getTrendRoleColor(index)}
              points={series.values
                .map((value, valueIndex) => {
                  const x = projectTrendX(valueIndex, chartData.labels.length, innerWidth);
                  const y = innerHeight - (value / maxValue) * innerHeight;
                  return `${x.toFixed(1)},${y.toFixed(1)}`;
                })
                .join(" ")}
            />
            {series.values.map((value, valueIndex) => {
              if (valueIndex !== series.values.length - 1) {
                return null;
              }
              const x = projectTrendX(valueIndex, chartData.labels.length, innerWidth);
              const y = innerHeight - (value / maxValue) * innerHeight;
              return (
                <circle
                  key={`${series.role}-${valueIndex}`}
                  cx={x}
                  cy={y}
                  r="4"
                  fill={getTrendRoleColor(index)}
                >
                  <title>
                    {prettifyLabel(series.role)}: {formatInteger(value)}
                  </title>
                </circle>
              );
            })}
          </g>
        ))}

        {activeHoverIndex !== null && hoverX !== null ? (
          <g className="cy-trend-hover-layer">
            <line
              className="cy-trend-hover-line"
              x1={hoverX}
              x2={hoverX}
              y1="0"
              y2={innerHeight}
            />
            {chartData.series.map((series, index) => {
              const value = series.values[activeHoverIndex] ?? 0;
              const y = innerHeight - (value / maxValue) * innerHeight;
              return (
                <circle
                  key={`${series.role}-hover`}
                  className="cy-trend-hover-dot"
                  cx={hoverX}
                  cy={y}
                  r="5.5"
                  fill={getTrendRoleColor(index)}
                />
              );
            })}
          </g>
        ) : null}

        <rect
          className="cy-trend-hover-target"
          x="0"
          y="0"
          width={innerWidth}
          height={innerHeight}
          onPointerMove={handlePointerMove}
          onPointerLeave={() => setHoverIndex(null)}
        />
      </g>

      {activeHoverIndex !== null ? (
        <g className="cy-trend-tooltip" transform={`translate(${tooltipX} ${tooltipY})`}>
          <rect
            className="cy-trend-tooltip-panel"
            width={tooltipWidth}
            height={tooltipHeight}
            rx="8"
            ry="8"
          />
          <text className="cy-trend-tooltip-title" x="16" y="25">
            {formatTrendTooltipDate(chartData.labels[activeHoverIndex], granularity)}
          </text>
          <text className="cy-trend-tooltip-total" x={tooltipWidth - 16} y="25" textAnchor="end">
            Total {formatInteger(tooltipRows.reduce((sum, row) => sum + row.value, 0))}
          </text>
          {tooltipRows.map((row, index) => (
            <g key={row.role} transform={`translate(16 ${50 + index * 22})`}>
              <circle cx="4" cy="-4" r="4" fill={row.color} />
              <text className="cy-trend-tooltip-label" x="16" y="0">
                {prettifyLabel(row.role)}
              </text>
              <text
                className="cy-trend-tooltip-value"
                x={tooltipWidth - 32}
                y="0"
                textAnchor="end"
              >
                {formatInteger(row.value)}
              </text>
            </g>
          ))}
        </g>
      ) : null}
    </svg>
  );
}

function SwissVacancyMap({
  items,
  coverage,
  selectedCityKey,
  selectedCityDetails,
  cityOptions,
  onSelectCity,
}) {
  const maxValue = Math.max(...items.map((item) => item.vacancy_count), 1);
  const markerItems = [...items].sort((a, b) => a.vacancy_count - b.vacancy_count);
  const labelItems = items.filter(
    (item) =>
      CANTON_CAPITAL_CITY_KEYS.has(item.key) && item.vacancy_count >= MAP_CITY_LABEL_MIN_VACANCIES,
  );

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
          {coverage ? (
            <p className="cy-copy cy-map-coverage-copy">
              {formatInteger(Math.round(coverage.mappedVacancies))} of{" "}
              {formatInteger(Math.round(coverage.totalVacancies))} tracked vacancies are placed on
              the city map ({formatPercent(coverage.mappedShare)} coverage).
            </p>
          ) : null}
        </div>
        <div className="cy-map-summary" aria-label="Mapped vacancy summary">
          <span>{formatInteger(items.length)} cities</span>
          <strong>{formatInteger(Math.round(coverage?.mappedVacancies ?? 0))} mapped vacancies</strong>
          {coverage ? (
            <div className="cy-map-summary-breakdown">
              <p>
                <strong>{formatInteger(Math.round(coverage.multiCityVacancies))}</strong> mention
                multiple cities and are split across bubbles.
              </p>
              <p>
                <strong>{formatInteger(Math.round(coverage.broadLocationVacancies))}</strong> use
                nationwide, regional, or remote-style location labels.
              </p>
              <p>
                <strong>{formatInteger(Math.round(coverage.missingLocationVacancies))}</strong>{" "}
                are unknown and{" "}
                <strong>{formatInteger(Math.round(coverage.unmatchedLocationVacancies))}</strong>{" "}
                more still use labels not mapped to a city.
              </p>
            </div>
          ) : null}
        </div>
      </div>

      <div className="cy-map-layout">
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
                const isSelected = item.key === selectedCityKey;

                return (
                  <g
                    key={item.key}
                    className="cy-map-marker"
                    transform={`translate(${x} ${y})`}
                    role="button"
                    tabIndex={0}
                    aria-pressed={isSelected}
                    onClick={() => onSelectCity(item.key)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSelectCity(item.key);
                      }
                    }}
                  >
                    <circle
                      className={`cy-map-bubble ${isSelected ? "cy-map-bubble-selected" : ""}`}
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
                const isSelected = item.key === selectedCityKey;

                return (
                  <text
                    key={`${item.key}-label`}
                    className={isSelected ? "cy-map-label-selected" : ""}
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

        <MapCityDetailPanel
          details={selectedCityDetails}
          cityOptions={cityOptions}
          onSelectCity={onSelectCity}
        />
      </div>
    </article>
  );
}

function MapCityDetailPanel({ details, cityOptions, onSelectCity }) {
  if (!details) {
    return (
      <aside className="cy-map-detail-panel">
        <p className="cy-kicker">City detail</p>
        <h3>Select a city bubble</h3>
        <p className="cy-copy">
          Click a bubble on the map to inspect local hiring volume, share of the market, top roles,
          employers, and work mode mix.
        </p>
      </aside>
    );
  }

  const topRoles = selectTopItems(filterUnknown(details.roleDistribution ?? []), MAP_DETAIL_ROLE_LIMIT);
  const topEmployers = selectTopItems(
    filterUnknown(details.companyDistribution ?? []),
    MAP_DETAIL_EMPLOYER_LIMIT,
  );
  const workModeItems = selectTopItems(
    filterUnknown(details.workModeDistribution ?? []),
    details.workModeDistribution?.length ?? 4,
  );

  return (
    <aside className="cy-map-detail-panel" aria-live="polite">
      <div className="cy-map-detail-head">
        <div>
          <p className="cy-kicker">City detail</p>
          <h3>{details.label}</h3>
        </div>
        <span className="cy-map-detail-rank">#{details.rank} mapped city</span>
      </div>

      <MapCityPicker
        selectedCityKey={details.key}
        cityOptions={cityOptions}
        onSelectCity={onSelectCity}
      />

      <div className="cy-map-detail-stats">
        <MapDetailStat
          label="Vacancies"
          value={formatInteger(Math.round(details.vacancy_count))}
        />
        <MapDetailStat label="Market share" value={formatPercent(details.share)} />
      </div>

      <div className="cy-map-detail-block">
        <div className="cy-data-panel-head">
          <h4>Top roles</h4>
        </div>
        {topRoles.length ? (
          <HorizontalBarChart
            items={topRoles}
            labelKey="role_category"
            valueKey="vacancy_count"
            shareKey="share"
          />
        ) : (
          <p className="cy-copy cy-empty-state">No role breakdown available.</p>
        )}
      </div>

      <div className="cy-map-detail-block">
        <div className="cy-data-panel-head">
          <h4>Top employers</h4>
        </div>
        {topEmployers.length ? (
          <HorizontalBarChart
            items={topEmployers}
            labelKey="company"
            valueKey="vacancy_count"
            shareKey="share"
            labelFormatter={(value) => value || "n/a"}
          />
        ) : (
          <p className="cy-copy cy-empty-state">No employer breakdown available.</p>
        )}
      </div>

      <div className="cy-map-detail-block">
        <div className="cy-data-panel-head">
          <h4>Work mode split</h4>
        </div>
        {workModeItems.length ? (
          <SegmentChart items={workModeItems} />
        ) : (
          <p className="cy-copy cy-empty-state">No work mode breakdown available.</p>
        )}
      </div>
    </aside>
  );
}

function MapCityPicker({ selectedCityKey, cityOptions, onSelectCity }) {
  const containerRef = useRef(null);
  const inputRef = useRef(null);
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlightedIndex, setHighlightedIndex] = useState(0);

  const selectedCity =
    cityOptions.find((item) => item.key === selectedCityKey) ?? cityOptions[0] ?? null;
  const normalizedQuery = query.trim().toLowerCase();
  const selectedCityLabel = selectedCity?.label ?? "";
  const shouldFilterOptions =
    isOpen && normalizedQuery && normalizedQuery !== selectedCityLabel.toLowerCase();
  const filteredOptions = shouldFilterOptions
    ? cityOptions.filter((item) => item.label.toLowerCase().includes(normalizedQuery))
    : cityOptions;

  useEffect(() => {
    if (selectedCityLabel) {
      setQuery(selectedCityLabel);
    }
  }, [selectedCityLabel]);

  useEffect(() => {
    if (highlightedIndex < 0 || highlightedIndex >= filteredOptions.length) {
      setHighlightedIndex(0);
    }
  }, [filteredOptions.length, highlightedIndex]);

  useEffect(() => {
    function handlePointerDown(event) {
      if (!containerRef.current?.contains(event.target)) {
        setIsOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, []);

  function openMenu() {
    const selectedIndex = filteredOptions.findIndex((item) => item.key === selectedCityKey);
    setIsOpen(true);
    setHighlightedIndex(selectedIndex >= 0 ? selectedIndex : 0);
  }

  function handleSelect(item) {
    setQuery(item.label);
    setIsOpen(false);
    setHighlightedIndex(0);
    onSelectCity(item.key);
  }

  function handleInputFocus() {
    openMenu();
    window.requestAnimationFrame(() => {
      inputRef.current?.select();
    });
  }

  function handleInputChange(event) {
    setQuery(event.target.value);
    setIsOpen(true);
    setHighlightedIndex(0);
  }

  function handleInputKeyDown(event) {
    if (!filteredOptions.length && event.key === "Escape") {
      setIsOpen(false);
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!isOpen) {
        openMenu();
        return;
      }
      if (!filteredOptions.length) {
        return;
      }
      setHighlightedIndex((current) => Math.min(current + 1, filteredOptions.length - 1));
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!isOpen) {
        openMenu();
        return;
      }
      if (!filteredOptions.length) {
        return;
      }
      setHighlightedIndex((current) => Math.max(current - 1, 0));
      return;
    }

    if (event.key === "Enter") {
      if (isOpen && filteredOptions[highlightedIndex]) {
        event.preventDefault();
        handleSelect(filteredOptions[highlightedIndex]);
      }
      return;
    }

    if (event.key === "Escape") {
      setQuery(selectedCity?.label ?? "");
      setIsOpen(false);
    }
  }

  return (
    <div className="cy-map-city-picker" ref={containerRef}>
      <div className="cy-map-city-picker-head">
        <span>Choose another city</span>
        <p>Type to search or use arrow keys.</p>
      </div>

      <div className="cy-map-city-picker-field">
        <input
          ref={inputRef}
          className="cy-map-city-picker-input"
          type="text"
          value={query}
          placeholder="Search city"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={isOpen}
          aria-controls="city-map-picker-listbox"
          onFocus={handleInputFocus}
          onChange={handleInputChange}
          onKeyDown={handleInputKeyDown}
        />
      </div>

      {isOpen ? (
        <div className="cy-map-city-picker-menu" role="listbox" id="city-map-picker-listbox">
          {filteredOptions.length ? (
            filteredOptions.map((item, index) => {
              const isSelected = item.key === selectedCityKey;
              const isHighlighted = index === highlightedIndex;

              return (
                <button
                  key={item.key}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  className={[
                    "cy-map-city-picker-option",
                    isSelected ? "is-selected" : "",
                    isHighlighted ? "is-highlighted" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  onMouseEnter={() => setHighlightedIndex(index)}
                  onClick={() => handleSelect(item)}
                >
                  <span>{item.label}</span>
                  <strong>{formatInteger(Math.round(item.vacancy_count))}</strong>
                </button>
              );
            })
          ) : (
            <p className="cy-map-city-picker-empty">No matching city found.</p>
          )}
        </div>
      ) : null}
    </div>
  );
}

function MapDetailStat({ label, value }) {
  return (
    <div className="cy-map-detail-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function HorizontalBarChart({ items, labelKey, valueKey, shareKey, labelFormatter = prettifyLabel }) {
  const maxValue = Math.max(...items.map((item) => item[valueKey] ?? 0), 1);

  return (
    <div className="cy-bar-list">
      {items.map((item) => (
        <div key={item.key ?? item[labelKey]} className="cy-bar-list-row">
          <div className="cy-bar-list-head">
            <span>{labelFormatter(item[labelKey])}</span>
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

function SkillRoleMatrix({ matrix }) {
  if (!matrix.rows.length || !matrix.skills.length) {
    return <p className="cy-copy cy-empty-state">No role skill matrix available.</p>;
  }

  return (
    <div className="cy-skill-matrix">
      <div className="cy-skill-matrix-legend" aria-label="Skill legend">
        {matrix.skills.map((skill) => (
          <span key={skill.skill}>
            <i style={{ background: skill.color }} />
            {prettifyLabel(skill.skill)}
          </span>
        ))}
      </div>

      <div className="cy-skill-matrix-grid" role="table" aria-label="Skills by role">
        {matrix.rows.map((row) => (
          <div key={row.role} className="cy-skill-matrix-row" role="row">
            <div className="cy-skill-matrix-role" role="rowheader">
              {prettifyLabel(row.role)}
            </div>
            <div className="cy-skill-matrix-track" role="cell">
              {row.segments.map((segment) => (
                <span
                  key={`${row.role}-${segment.skill}`}
                  className="cy-skill-matrix-segment"
                  style={{
                    flexGrow: Math.max(segment.normalizedShare * 100, 1.2),
                    background: segment.color,
                  }}
                  title={`${prettifyLabel(row.role)} · ${prettifyLabel(
                    segment.skill,
                  )}: ${formatInteger(segment.vacancy_count)} vacancies, ${formatPercent(
                    segment.share_within_group,
                  )}`}
                />
              ))}
            </div>
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

function buildSwissCityMapCoverage(items, totalVacancies) {
  let mappedVacancies = 0;
  let multiCityVacancies = 0;
  let broadLocationVacancies = 0;
  let missingLocationVacancies = 0;
  let unmatchedLocationVacancies = 0;
  let computedTotalVacancies = 0;

  for (const item of items) {
    const value = item?.vacancy_count;
    if (typeof value !== "number" || value <= 0) {
      continue;
    }

    computedTotalVacancies += value;
    const cityKeys = resolveCityKeys(item.label ?? item.key);
    if (cityKeys.length) {
      mappedVacancies += value;
      if (cityKeys.length > 1) {
        multiCityVacancies += value;
      }
      continue;
    }

    const classification = classifyUnmappedCityLabel(item.label ?? item.key);
    if (classification === "broad") {
      broadLocationVacancies += value;
    } else if (classification === "missing") {
      missingLocationVacancies += value;
    } else {
      unmatchedLocationVacancies += value;
    }
  }

  const normalizedTotalVacancies =
    typeof totalVacancies === "number" && totalVacancies > 0
      ? totalVacancies
      : computedTotalVacancies;

  return {
    totalVacancies: normalizedTotalVacancies,
    mappedVacancies,
    mappedShare: normalizedTotalVacancies ? mappedVacancies / normalizedTotalVacancies : 0,
    unmappedVacancies:
      broadLocationVacancies + missingLocationVacancies + unmatchedLocationVacancies,
    multiCityVacancies,
    broadLocationVacancies,
    missingLocationVacancies,
    unmatchedLocationVacancies,
  };
}

function buildSwissCityDetailMap(items, totalVacancies) {
  const detailMap = new Map();

  for (const item of items ?? []) {
    const vacancyCount = Number(item?.vacancy_count);
    if (!Number.isFinite(vacancyCount) || vacancyCount <= 0) {
      continue;
    }

    const cityKeys = resolveCityKeys(item.city);
    if (!cityKeys.length) {
      continue;
    }

    const weight = 1 / cityKeys.length;
    for (const cityKey of cityKeys) {
      const city = CITY_LOCATION_BY_KEY.get(cityKey);
      if (!city) {
        continue;
      }

      const detail = detailMap.get(cityKey) ?? createSwissCityDetailEntry(city);
      detail.vacancy_count += vacancyCount * weight;
      accumulateWeightedDistribution(
        detail.roleDistributionMap,
        item.role_distribution,
        "role_category",
        weight,
      );
      accumulateWeightedDistribution(
        detail.companyDistributionMap,
        item.company_distribution,
        "company",
        weight,
      );
      accumulateWeightedDistribution(
        detail.workModeDistributionMap,
        item.work_mode_distribution,
        "work_mode",
        weight,
      );
      detailMap.set(cityKey, detail);
    }
  }

  const normalizedTotalVacancies =
    typeof totalVacancies === "number" && totalVacancies > 0 ? totalVacancies : 0;
  const sortedDetails = [...detailMap.values()]
    .map((detail) => ({
      key: detail.key,
      label: detail.label,
      vacancy_count: detail.vacancy_count,
      share: normalizedTotalVacancies ? detail.vacancy_count / normalizedTotalVacancies : 0,
      roleDistribution: finalizeWeightedDistribution(
        detail.roleDistributionMap,
        "role_category",
        detail.vacancy_count,
      ),
      companyDistribution: finalizeWeightedDistribution(
        detail.companyDistributionMap,
        "company",
        detail.vacancy_count,
      ),
      workModeDistribution: finalizeWeightedDistribution(
        detail.workModeDistributionMap,
        "work_mode",
        detail.vacancy_count,
      ),
    }))
    .sort((left, right) => {
      if (right.vacancy_count !== left.vacancy_count) {
        return right.vacancy_count - left.vacancy_count;
      }
      return left.label.localeCompare(right.label, "en-US");
    });

  sortedDetails.forEach((detail, index) => {
    detail.rank = index + 1;
  });
  return new Map(sortedDetails.map((detail) => [detail.key, detail]));
}

function createSwissCityDetailEntry(city) {
  return {
    key: city.key,
    label: city.label,
    vacancy_count: 0,
    roleDistributionMap: new Map(),
    companyDistributionMap: new Map(),
    workModeDistributionMap: new Map(),
  };
}

function accumulateWeightedDistribution(targetMap, items, labelKey, weight) {
  for (const item of items ?? []) {
    const label = item?.[labelKey];
    const vacancyCount = Number(item?.vacancy_count);
    if (!label || !Number.isFinite(vacancyCount) || vacancyCount <= 0) {
      continue;
    }
    targetMap.set(label, (targetMap.get(label) ?? 0) + vacancyCount * weight);
  }
}

function finalizeWeightedDistribution(itemsMap, labelKey, totalVacancyCount) {
  return [...itemsMap.entries()]
    .map(([label, vacancyCount]) => ({
      key: label,
      label,
      [labelKey]: label,
      vacancy_count: vacancyCount,
      share: totalVacancyCount ? vacancyCount / totalVacancyCount : 0,
    }))
    .sort((left, right) => {
      if (right.vacancy_count !== left.vacancy_count) {
        return right.vacancy_count - left.vacancy_count;
      }
      return String(left.label).localeCompare(String(right.label), "en-US");
    });
}

function buildSkillRoleMatrix(groups, roleLimit, skillLimit) {
  const roleGroups = (groups ?? [])
    .filter((group) => group.group && group.group !== "Unknown" && Array.isArray(group.items))
    .map((group) => ({
      role: group.group,
      items: group.items.filter((item) => item.skill && item.skill !== "Unknown"),
      total: group.items.reduce((sum, item) => sum + (item.vacancy_count ?? 0), 0),
    }))
    .filter((group) => group.total > 0)
    .sort((a, b) => b.total - a.total || a.role.localeCompare(b.role, "en-US"))
    .slice(0, roleLimit);
  const skillTotals = new Map();

  for (const group of roleGroups) {
    for (const item of group.items) {
      skillTotals.set(item.skill, (skillTotals.get(item.skill) ?? 0) + (item.vacancy_count ?? 0));
    }
  }

  const skills = [...skillTotals.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "en-US"))
    .slice(0, skillLimit)
    .map(([skill], index) => ({
      skill,
      color: SKILL_MATRIX_COLORS[index % SKILL_MATRIX_COLORS.length],
    }));
  const colorBySkill = new Map(skills.map((skill) => [skill.skill, skill.color]));
  const rows = roleGroups
    .map((group) => {
      const segments = skills
        .map((skill) => {
          const item = group.items.find((candidate) => candidate.skill === skill.skill);
          return item
            ? {
                skill: skill.skill,
                color: colorBySkill.get(skill.skill),
                vacancy_count: item.vacancy_count ?? 0,
                share_within_group: item.share_within_group ?? 0,
              }
            : null;
        })
        .filter(Boolean);
      const visibleTotal = segments.reduce((sum, segment) => sum + segment.vacancy_count, 0);

      return {
        role: group.role,
        segments: segments.map((segment) => ({
          ...segment,
          normalizedShare: visibleTotal ? segment.vacancy_count / visibleTotal : 0,
        })),
      };
    })
    .filter((row) => row.segments.length);

  return { skills, rows };
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

function classifyUnmappedCityLabel(value) {
  const normalizedValue = normalizeCityLabel(value);
  if (!normalizedValue || normalizedValue === "unknown") {
    return "missing";
  }

  if (isBroadSwissLocationLabel(value)) {
    return "broad";
  }

  return "unmatched";
}

function isBroadSwissLocationLabel(value) {
  const rawValue = String(value ?? "");
  return /remote|home\s*office|hybrid|switzerland|schweiz|suisse|svizzera|metropolitan area|district|canton|region|romandy|ostschweiz|deutschschweiz|central switzerland/i.test(
    rawValue,
  );
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

function filterTrendItemsByPeriod(items, periodDays, granularity) {
  if (!Array.isArray(items) || !items.length || periodDays === null) {
    return items ?? [];
  }

  const dateKey = granularity === "daily" ? "date" : "week_start";
  const latestTime = Math.max(
    ...items.map((item) => new Date(item[dateKey]).getTime()).filter(Number.isFinite),
  );
  if (!Number.isFinite(latestTime)) {
    return items;
  }

  const startTime = latestTime - (periodDays - 1) * 24 * 60 * 60 * 1000;
  return items.filter((item) => {
    const itemTime = new Date(item[dateKey]).getTime();
    return Number.isFinite(itemTime) && itemTime >= startTime && itemTime <= latestTime;
  });
}

function getTrendSegments(trends, granularity) {
  if (granularity === "daily") {
    return trends?.segments?.daily ?? [];
  }
  return trends?.segments?.weekly ?? [];
}

function getTrendCantonOptions(items) {
  return [...new Set((items ?? []).map((item) => item.canton).filter(isKnownTrendValue))].sort(
    (a, b) => a.localeCompare(b, "en-US"),
  );
}

function filterTrendSegmentsByCantons(items, selectedCantons) {
  if (!selectedCantons.length) {
    return items ?? [];
  }

  const selected = new Set(selectedCantons);
  return (items ?? []).filter((item) => selected.has(item.canton));
}

function filterTrendSegmentsByRoles(items, selectedRoles) {
  if (!selectedRoles.length) {
    return items ?? [];
  }

  const selected = new Set(selectedRoles);
  return (items ?? []).filter((item) => selected.has(item.role_category));
}

function getTopTrendRoles(items, limit) {
  const totals = new Map();
  for (const item of items ?? []) {
    const role = item.role_category;
    if (!isKnownTrendValue(role)) {
      continue;
    }
    totals.set(role, (totals.get(role) ?? 0) + (item.published_count ?? 0));
  }

  return [...totals.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "en-US"))
    .slice(0, limit)
    .map(([role]) => role);
}

function buildTrendLineChartData(items, roles, granularity) {
  const dateKey = granularity === "daily" ? "date" : "week_start";
  const labels = [...new Set((items ?? []).map((item) => item[dateKey]).filter(Boolean))].sort();
  const countsByRoleDate = new Map();

  for (const item of items ?? []) {
    const role = item.role_category;
    const label = item[dateKey];
    if (!role || !label) {
      continue;
    }

    const key = `${role}|${label}`;
    countsByRoleDate.set(key, (countsByRoleDate.get(key) ?? 0) + (item.published_count ?? 0));
  }

  const series = roles.map((role) => ({
    role,
    values: labels.map((label) => countsByRoleDate.get(`${role}|${label}`) ?? 0),
  }));
  const maxValue = Math.max(...series.flatMap((line) => line.values), 1);

  return { labels, series, maxValue };
}

function calculateSegmentTrendGrowth(items, periodDays, granularity) {
  const dateKey = granularity === "daily" ? "date" : "week_start";
  const labels = [...new Set((items ?? []).map((item) => item[dateKey]).filter(Boolean))].sort();
  if (!labels.length) {
    return null;
  }

  const totalsByLabel = new Map();
  for (const item of items ?? []) {
    const label = item[dateKey];
    if (!label) {
      continue;
    }
    totalsByLabel.set(label, (totalsByLabel.get(label) ?? 0) + (item.published_count ?? 0));
  }

  if (periodDays === null) {
    const midpoint = Math.floor(labels.length / 2);
    return calculateGrowthFromLabels(
      labels.slice(midpoint),
      labels.slice(0, midpoint),
      totalsByLabel,
    );
  }

  const latestTime = Math.max(...labels.map((label) => new Date(label).getTime()));
  if (!Number.isFinite(latestTime)) {
    return null;
  }

  const dayMs = 24 * 60 * 60 * 1000;
  const currentStart = latestTime - (periodDays - 1) * dayMs;
  const previousStart = currentStart - periodDays * dayMs;
  const previousEnd = currentStart - dayMs;
  const currentLabels = labels.filter((label) => {
    const time = new Date(label).getTime();
    return Number.isFinite(time) && time >= currentStart && time <= latestTime;
  });
  const previousLabels = labels.filter((label) => {
    const time = new Date(label).getTime();
    return Number.isFinite(time) && time >= previousStart && time <= previousEnd;
  });

  return calculateGrowthFromLabels(currentLabels, previousLabels, totalsByLabel);
}

function calculateGrowthFromLabels(currentLabels, previousLabels, totalsByLabel) {
  const currentCount = currentLabels.reduce(
    (sum, label) => sum + (totalsByLabel.get(label) ?? 0),
    0,
  );
  const previousCount = previousLabels.reduce(
    (sum, label) => sum + (totalsByLabel.get(label) ?? 0),
    0,
  );
  if (!previousCount) {
    return null;
  }
  return (currentCount - previousCount) / previousCount;
}

function getTrendRoleSeasonality(items) {
  const totalsByMonth = new Map();
  for (const item of items ?? []) {
    if (!item.date) {
      continue;
    }
    const date = new Date(item.date);
    if (Number.isNaN(date.getTime())) {
      continue;
    }
    const month = date.getUTCMonth() + 1;
    totalsByMonth.set(month, (totalsByMonth.get(month) ?? 0) + (item.published_count ?? 0));
  }

  return [...totalsByMonth.entries()]
    .map(([month, vacancy_count]) => ({ month, vacancy_count }))
    .sort((a, b) => a.month - b.month);
}

function getStrongestSeasonalityMonth(items) {
  return [...items].sort((a, b) => (b.vacancy_count ?? 0) - (a.vacancy_count ?? 0))[0] ?? null;
}

function getWeakestSeasonalityMonth(items) {
  return [...items].sort((a, b) => (a.vacancy_count ?? 0) - (b.vacancy_count ?? 0))[0] ?? null;
}

function isKnownTrendValue(value) {
  return Boolean(value && value !== "Unknown" && value !== "unknown");
}

function getTrendRoleColor(index) {
  return TREND_ROLE_COLORS[index % TREND_ROLE_COLORS.length];
}

function buildYAxisTicks(maxValue) {
  const targetTickCount = 5;
  const roughStep = Math.max(maxValue / (targetTickCount - 1), 1);
  const magnitude = 10 ** Math.floor(Math.log10(roughStep));
  const normalizedStep = roughStep / magnitude;
  const niceStep =
    normalizedStep <= 1 ? 1 : normalizedStep <= 2 ? 2 : normalizedStep <= 5 ? 5 : 10;
  const step = niceStep * magnitude;
  const top = Math.ceil(maxValue / step) * step;
  const ticks = [];

  for (let value = 0; value <= top; value += step) {
    ticks.push(value);
  }

  return ticks.length >= 2 ? ticks : [0, top || 1];
}

function projectTrendX(index, count, width) {
  if (count <= 1) {
    return 0;
  }
  return (index / (count - 1)) * width;
}

function getTrendChartWidth(labelCount, granularity) {
  if (granularity !== "daily") {
    return 1040;
  }
  return Math.max(1040, labelCount * 18);
}

function buildTrendXAxisStep(labelCount, innerWidth, granularity) {
  if (labelCount <= 1) {
    return 1;
  }
  const minLabelSpacing = granularity === "daily" ? 84 : 112;
  const tickCapacity = Math.max(Math.floor(innerWidth / minLabelSpacing), 1);
  return Math.max(Math.ceil(labelCount / tickCapacity), 1);
}

function formatTrendAxisLabel(value, granularity) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value ?? "";
  }
  return new Intl.DateTimeFormat("en-CH", {
    month: "short",
    day: granularity === "daily" ? "numeric" : undefined,
    timeZone: "Europe/Zurich",
  }).format(date);
}

function formatTrendTooltipDate(value, granularity) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value ?? "";
  }

  const formattedDate = new Intl.DateTimeFormat("en-CH", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "Europe/Zurich",
  }).format(date);
  return granularity === "weekly" ? `Week of ${formattedDate}` : formattedDate;
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

function getRoleGroupSkillHighlights(groups, roleKey, limit = 3) {
  if (!roleKey) {
    return [];
  }

  const group = (groups ?? []).find((item) => item.group === roleKey);
  return selectTopItems(group?.items ?? [], limit).map((item) => item.skill).filter(Boolean);
}

function compareExperienceRequirements(first, second) {
  const firstExperience = getComparableExperienceYears(first);
  const secondExperience = getComparableExperienceYears(second);
  if (firstExperience !== secondExperience) {
    return secondExperience - firstExperience;
  }

  const firstMentions = first.experience_years_count ?? 0;
  const secondMentions = second.experience_years_count ?? 0;
  if (firstMentions !== secondMentions) {
    return secondMentions - firstMentions;
  }

  return String(first.seniority ?? "").localeCompare(String(second.seniority ?? ""));
}

function getComparableExperienceYears(item) {
  if (
    item.experience_years_count < EXPERIENCE_MIN_SAMPLE_SIZE ||
    typeof item.average_min_experience_years !== "number"
  ) {
    return Number.NEGATIVE_INFINITY;
  }

  return item.average_min_experience_years;
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

function formatSignedPercent(value) {
  if (typeof value !== "number") {
    return "n/a";
  }
  const sign = value > 0 ? "+" : "";
  const absoluteValue = Math.abs(value);
  const digits = absoluteValue >= 0.1 ? 1 : 2;
  return `${sign}${(value * 100).toFixed(digits)}%`;
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

function formatYears(value) {
  if (typeof value !== "number") {
    return "n/a";
  }
  return `${new Intl.NumberFormat("en-CH", {
    maximumFractionDigits: value >= 10 ? 0 : 1,
  }).format(value)} yrs`;
}

function formatCantonCode(value) {
  if (!value) {
    return "n/a";
  }
  return String(value).trim().toLocaleUpperCase("en-US");
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

function buildKeyFindings({ topCity, leadingRole, fastestGrowingRole, salarySummary }) {
  const findings = [];

  if (topCity) {
    findings.push({
      label: "Location",
      title: `${prettifyLabel(topCity.label)} keeps the largest share`,
      description: `${formatPercent(topCity.share)} of tracked vacancies are clustered there.`,
    });
  }

  if (fastestGrowingRole) {
    findings.push({
      label: "Momentum",
      title: `${prettifyLabel(fastestGrowingRole.role)} is growing fastest`,
      description: `${formatInteger(fastestGrowingRole.current)} postings in the last 30 days, ${formatMultiplier(
        fastestGrowingRole.growth,
      )} vs the previous 30-day window.`,
    });
  }

  if (typeof salarySummary?.salary_coverage === "number") {
    findings.push({
      label: "Compensation",
      title: "Salary coverage is still limited",
      description: `${formatInteger(salarySummary.salary_count)} listings expose usable pay data, or ${formatPercent(
        salarySummary.salary_coverage,
      )} of the snapshot.`,
    });
  }

  if (leadingRole) {
    findings.push({
      label: "Demand",
      title: `${prettifyLabel(leadingRole.label)} still anchors hiring`,
      description: `${formatPercent(leadingRole.share)} of tracked vacancies fall into this role category.`,
    });
  }

  return findings.slice(0, 4);
}

function getFastestGrowingRole(vacancyTrends) {
  const items = vacancyTrends?.segments?.daily ?? [];
  const latestDateValue = vacancyTrends?.summary?.latest_publication_date;
  if (!items.length || !latestDateValue) {
    return null;
  }

  const latestDate = new Date(`${latestDateValue}T00:00:00Z`);
  if (Number.isNaN(latestDate.getTime())) {
    return null;
  }

  const DAY_MS = 24 * 60 * 60 * 1000;
  const currentWindowStart = new Date(latestDate.getTime() - 29 * DAY_MS);
  const previousWindowStart = new Date(latestDate.getTime() - 59 * DAY_MS);
  const previousWindowEnd = new Date(latestDate.getTime() - 30 * DAY_MS);
  const totalsByRole = new Map();

  for (const item of items) {
    const role = item.role_category;
    if (!role || role === "Unknown") {
      continue;
    }

    const dateValue = item.date;
    const date = new Date(`${dateValue}T00:00:00Z`);
    if (Number.isNaN(date.getTime())) {
      continue;
    }

    const current = totalsByRole.get(role) ?? { role, current: 0, previous: 0 };

    if (date >= currentWindowStart && date <= latestDate) {
      current.current += item.published_count ?? 0;
    } else if (date >= previousWindowStart && date <= previousWindowEnd) {
      current.previous += item.published_count ?? 0;
    }

    totalsByRole.set(role, current);
  }

  const rankedRoles = [...totalsByRole.values()]
    .filter((item) => item.current > 0 && item.previous > 0)
    .map((item) => ({
      ...item,
      growth: (item.current - item.previous) / item.previous,
      delta: item.current - item.previous,
    }))
    .sort((first, second) => {
      if (second.growth !== first.growth) {
        return second.growth - first.growth;
      }
      return second.delta - first.delta;
    });

  return rankedRoles[0] ?? null;
}

function formatMultiplier(value) {
  if (typeof value !== "number") {
    return "n/a";
  }

  return `${(value + 1).toFixed(value >= 1 ? 1 : 2)}x`;
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
