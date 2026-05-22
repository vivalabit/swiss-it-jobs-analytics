export const DEFAULT_LANGUAGE = "en";

export const LANGUAGE_OPTIONS = [
  { code: "en", label: "English", shortLabel: "EN" },
  { code: "de", label: "Deutsch", shortLabel: "DE" },
];

export const LANGUAGE_LOCALES = {
  en: "en-CH",
  de: "de-CH",
};

export const LANGUAGE_COPY = {
  en: {
    documentTitle: "Swiss IT Job Market",
    languageSwitcher: {
      label: "Language",
      ariaLabel: "Select language",
    },
    common: {
      live: "Live",
      more: "More",
      less: "Less",
      allInputsPresent: "All expected CSV inputs are present.",
      moreFiles: (count) => `+${count} more`,
      na: "n/a",
    },
    sections: {
      overview: "Overview",
      snapshot: "Snapshot",
      findings: "Findings",
      "vacancy-trends": "Trends",
      "vacancy-map": "Map",
      charts: "Charts",
      experience: "Experience",
      salary: "Salary",
      skills: "Skills",
      metadata: "Methodology",
    },
    status: {
      loadingTitle: "Loading public snapshots",
      loadingMessage: "Fetching Swiss IT market statistics from generated JSON exports.",
      errorTitle: "Snapshot data unavailable",
      errorFallback: "The public snapshots could not be loaded.",
      fetchError: "Failed to load public statistics snapshots.",
    },
    hero: {
      titleAccent: "Swiss",
      titleRest: "IT Job Market",
      text:
        "Track hiring volume, salary benchmarks, and location hotspots from the latest public Swiss IT vacancy data.",
      dashboardCta: "Explore the dashboard",
      methodologyCta: "Read methodology",
      vacanciesTracked: "Vacancies tracked",
      published30d: (count) => `${count} published in 30 days`,
      currentCoverage: "current market coverage",
      medianSalary: "Median salary",
      salaryListings: (count) => `${count} listings with salary data`,
      salaryCoverage: "salary benchmark coverage",
      topHiringCity: "Top hiring city",
      activeVacancies: (count) => `${count} active vacancies`,
      cityDemand: "city demand",
    },
    snapshot: {
      kicker: "Snapshot context",
      title: "What this page is built on",
      description:
        "Quick context on freshness, sample size, coverage, and what the public export does not claim to measure.",
      sources: "Sources",
      sourceTitle: (count) => `${count} public job boards`,
      sourcesDescription: "Deduplicated at vacancy level before the public aggregate is published.",
      updated: "Updated",
      sampleSize: "Sample size",
      directEmployers: (count) => `${count} direct employers after agency filtering.`,
      salaryCoverage: "Salary coverage",
      salaryCoverageDescription: (count) =>
        `${count} listings with normalized CHF yearly salary data.`,
      includes: "Snapshot includes",
      coreSignals: "Core market signals",
      limitations: "Main limitations",
      limitationsTitle: "Read before comparing numbers",
      scopeItems: [
        "Vacancy volume",
        "Salary benchmarks",
        "Role and seniority mix",
        "City and canton demand",
        "Work mode split",
        "Skill and stack trends",
      ],
      limitationItems: [
        "Public aggregate snapshot, not a full census of the Swiss market.",
        "Salary benchmarks only use vacancies with explicit pay ranges.",
        "Salary rankings hide groups with fewer than 10 usable salary records.",
        "Coverage is limited to vacancies published from 2026 onward.",
        "Some fields are normalized or AI-assisted from posting text and structured metadata.",
      ],
    },
    findings: {
      kicker: "Key findings",
      title: "What stands out right now",
      location: "Location",
      locationTitle: (city) => `${city} keeps the largest share`,
      locationDescription: (share) => `${share} of tracked vacancies are clustered there.`,
      momentum: "Momentum",
      momentumTitle: (role) => `${role} is growing fastest`,
      momentumDescription: (count, multiplier) =>
        `${count} postings in the last 30 days, ${multiplier} vs the previous 30-day window.`,
      compensation: "Compensation",
      compensationTitle: "Salary benchmarks are low-confidence",
      compensationDescription: (count, share, minCount) =>
        `${count} listings expose usable pay data, or ${share} of the snapshot; rankings hide groups below ${minCount} records.`,
      demand: "Demand",
      demandTitle: (role) => `${role} still anchors hiring`,
      demandDescription: (share) => `${share} of tracked vacancies fall into this role category.`,
    },
    summary: {
      vacanciesDescription: "Current public export size across the Swiss tech market.",
      employersLabel: "Direct employers",
      employersDescription: "Distinct hiring companies after excluding recruiting agencies.",
      publishedLabel: "Published in 30d",
      publishedDescription: "Latest rolling-month intake of newly published vacancies.",
      salaryCoverageDescription: (count) =>
        `${count} vacancies with normalized yearly salary data.`,
    },
    charts: {
      mapTitlePrefix: "Swiss vacancy",
      mapTitleAccent: "map",
      dashboardTitlePrefix: "Analysis",
      dashboardTitleAccent: "dashboard",
      roleShare: "Role category share",
      leadingCantons: "Leading cantons",
      workMode: "Work mode distribution",
      seniorityMix: "Seniority mix",
      topCities: "Top cities",
      topEmployers: "Top direct employers",
      topEmployersDescription: "Recruiting agencies and job boards are excluded.",
    },
    salary: {
      sectionTitlePrefix: "Salary",
      sectionTitleSeparator: " ",
      sectionTitleAccent: "metrics",
      snapshotTitle: "Compensation snapshot",
      snapshotDescription: "Comparable CHF salaries normalized to yearly values.",
      breakdownAria: "Salary breakdown",
      roles: "Roles",
      seniority: "Seniority",
      averageYearly: "Average yearly",
      medianYearly: "Median yearly",
      salaryCoverage: "Salary coverage",
      records: "Records",
      seniorityChartTitle: "Seniority ranked by average salary",
      seniorityChartDescription:
        "Seniority levels with at least 10 normalized CHF salary records.",
      roleChartTitle: "Roles ranked by average salary",
      roleChartDescription: "Role categories with at least 10 normalized CHF salary records.",
      confidenceTitle: "Low-confidence salary benchmark",
      confidenceText: (minCount, hiddenCount, coverage, count) =>
        `Ranking only shows groups with at least ${minCount} salary records.${
          hiddenCount ? ` ${hiddenCount} thin-sample groups are hidden.` : ""
        } Overall salary coverage is ${coverage} from ${count} records.`,
      median: "Median",
      noMetrics: "No comparable salary metrics available.",
      salaries: "salaries",
    },
    skills: {
      sectionTitlePrefix: "Top",
      sectionTitleMiddle: "skills",
      sectionTitleSuffix: "and",
      sectionTitleLast: "pairings",
      topOverall: "Top overall skills",
      topOverallDescription: "Ranked by vacancy frequency.",
      skill: "Skill",
      vacancies: "Vacancies",
      share: "Share",
      frequentPairings: "Frequent pairings",
      frequentPairingsDescription: "Technologies that often appear together.",
      sharedVacancies: (count) => `${count} shared vacancies`,
      topLanguages: "Top programming languages",
      topLanguagesDescription:
        "Language mentions extracted from the current vacancy snapshot.",
      coverage: "Coverage",
      distinctLanguages: "Distinct languages",
      language: "Language",
      topFrameworks: "Top frameworks & libraries",
      topFrameworksDescription:
        "Framework and library mentions extracted from the current vacancy snapshot.",
      distinctItems: "Distinct items",
      frameworkLibrary: "Framework / Library",
      jobSkillsByRole: "Job skills by role",
      jobSkillsByRoleDescription:
        "Skill mix within the leading role categories. Segment width is normalized inside each role.",
      skillLegend: "Skill legend",
      skillsByRole: "Skills by role",
      noMatrix: "No role skill matrix available.",
    },
    methodology: {
      sectionTitlePrefix: "Read",
      sectionTitleAccent: "methodology",
      sectionDescription:
        "How the public snapshot is assembled, normalized, and published for the dashboard.",
      pipelineTitle: "Pipeline overview",
      pipelineDescription:
        "The dashboard is built from aggregated vacancy exports, AI-assisted vacancy enrichment, and compact public snapshot files.",
      steps: [
        "Collect processed vacancy exports from the multi-source analytics pipeline.",
        "Deduplicate and normalize companies, locations, work mode, seniority, and salary fields.",
        "Run AI-assisted vacancy analysis to improve classification accuracy and recover details that rule-based filters can miss.",
        "Convert salary data to comparable yearly CHF ranges before aggregation.",
        "Publish compact JSON snapshots and mirrored CSV extracts for the public dashboard.",
      ],
      coverageTitle: "Snapshot coverage",
      coverageDescription: "Current build metadata for the export powering this page.",
      generated: "Generated",
      jsonSnapshots: "JSON snapshots",
      jsonDescription: "Public files published to the dashboard.",
      csvInputs: "CSV inputs",
      csvDescription: "Analytics exports available for this build.",
      missingInputs: "Missing inputs",
      downloadJson: "Download JSON snapshots",
      downloadCsv: "Download CSV exports",
    },
    navigation: {
      ariaLabel: "Page sections",
      title: "Navigate",
    },
    experience: {
      title: "Experience requirements",
      description: (minSize) =>
        `Explicit years of experience requested in vacancy text, grouped by inferred seniority. Averages by seniority require at least ${minSize} year mentions.`,
      seniorityMentionLabel: (count) => `${count} year mentions with seniority`,
      yearsMentionedLabel: (count) => `${count} mention years of experience`,
      averageMinimum: "Average minimum requested",
      medianMinimum: "Median minimum requested",
      mentionsBySeniority: "Experience mentions by seniority",
      seniority: "Seniority",
      averageMinExperience: "Avg. min exp.",
      mentions: "Mentions",
      distributionTitle: "Seniority distribution",
      distributionDescription:
        "Overall inferred seniority mix across vacancies, independent of explicit experience mentions.",
      vacancies: "Vacancies",
      share: "Share",
    },
    trends: {
      kicker: "Publication date index",
      title: (location) => `Job postings in ${location}`,
      description:
        "Role-category posting trend with canton filters, inferred closures and seasonality.",
      filtersAria: "Vacancy trend filters",
      region: "Region",
      switzerland: "Switzerland",
      professions: "Professions",
      period: "Period",
      periodAria: "Period",
      granularityAria: "Granularity",
      days: "Days",
      weeks: "Weeks",
      publishedSelection: "Published in selection",
      growthPrevious: "Growth vs previous period",
      closedDisappeared: "Closed / disappeared",
      seasonalityHighLow: "Seasonality high / low",
      seasonalityHighLowWithMonth: (month) => `Seasonality high / low: ${month}`,
      legendAria: "Profession legend",
      closedFootnote: "Closed means last seen before the latest crawl.",
      trendFootnote: "Trend uses vacancy publication dates.",
      empty: "No trend data for this selection.",
      chartTitle: "Vacancy trend by profession",
      tooltipTotal: (count) => `Total ${count}`,
      weekOf: (date) => `Week of ${date}`,
      monthNames: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    },
    map: {
      emptyTitle: "Vacancies by Swiss city",
      emptyDescription: "No mappable Swiss city metrics available.",
      title: "Vacancies by Swiss city",
      description:
        "Red bubbles are scaled by vacancy count. Darker and larger bubbles represent stronger city concentration.",
      coverageDescription: (mapped, total, share) =>
        `${mapped} of ${total} tracked vacancies are placed on the city map (${share} coverage).`,
      summaryAria: "Mapped vacancy summary",
      cities: (count) => `${count} cities`,
      mappedVacancies: (count) => `${count} mapped vacancies`,
      multiCity: (count) => `${count} mention multiple cities and are split across bubbles.`,
      broadLocation: (count) =>
        `${count} use nationwide, regional, or remote-style location labels.`,
      unmapped: (unknown, unmatched) =>
        `${unknown} are unknown and ${unmatched} more still use labels not mapped to a city.`,
      svgTitle: "Swiss IT job vacancies by city",
      svgDescription:
        "Switzerland outline with red translucent circles over cities. Circle size and opacity increase with vacancy count.",
      markerTitle: (city, count) => `${city}: ${count} vacancies`,
      detailKicker: "City detail",
      selectCityTitle: "Select a city bubble",
      selectCityDescription:
        "Click a bubble on the map to inspect local hiring volume, share of the market, top roles, employers, and work mode mix.",
      rank: (rank) => `#${rank} mapped city`,
      vacancies: "Vacancies",
      marketShare: "Market share",
      topRoles: "Top roles",
      noRoles: "No role breakdown available.",
      topEmployers: "Top employers",
      noEmployers: "No employer breakdown available.",
      workMode: "Work mode split",
      noWorkMode: "No work mode breakdown available.",
      chooseCity: "Choose another city",
      searchHelp: "Type to search or use arrow keys.",
      searchPlaceholder: "Search city",
      noCity: "No matching city found.",
    },
  },
  de: {
    documentTitle: "Schweizer IT-Arbeitsmarkt",
    languageSwitcher: {
      label: "Sprache",
      ariaLabel: "Sprache auswählen",
    },
    common: {
      live: "Live",
      more: "Mehr",
      less: "Weniger",
      allInputsPresent: "Alle erwarteten CSV-Eingaben sind vorhanden.",
      moreFiles: (count) => `+${count} weitere`,
      na: "k.A.",
    },
    sections: {
      overview: "Überblick",
      snapshot: "Datengrundlage",
      findings: "Erkenntnisse",
      "vacancy-trends": "Trends",
      "vacancy-map": "Karte",
      charts: "Analysen",
      experience: "Erfahrung",
      salary: "Gehalt",
      skills: "Skills",
      metadata: "Methodik",
    },
    status: {
      loadingTitle: "Öffentliche Snapshots werden geladen",
      loadingMessage:
        "Schweizer IT-Marktdaten werden aus generierten JSON-Exporten geladen.",
      errorTitle: "Snapshot-Daten nicht verfügbar",
      errorFallback: "Die öffentlichen Snapshots konnten nicht geladen werden.",
      fetchError: "Öffentliche Statistik-Snapshots konnten nicht geladen werden.",
    },
    hero: {
      titleAccent: "Swiss",
      titleRest: "IT-Arbeitsmarkt",
      text:
        "Beobachte Einstellungsvolumen, Gehaltsbenchmarks und lokale Nachfragezentren anhand aktueller öffentlicher Schweizer IT-Stellendaten.",
      dashboardCta: "Dashboard ansehen",
      methodologyCta: "Methodik lesen",
      vacanciesTracked: "Erfasste Stellen",
      published30d: (count) => `${count} in 30 Tagen veröffentlicht`,
      currentCoverage: "aktuelle Marktabdeckung",
      medianSalary: "Median-Gehalt",
      salaryListings: (count) => `${count} Inserate mit Gehaltsdaten`,
      salaryCoverage: "Abdeckung der Gehaltsbenchmarks",
      topHiringCity: "Stärkste Stadt",
      activeVacancies: (count) => `${count} aktive Stellen`,
      cityDemand: "Stadtnachfrage",
    },
    snapshot: {
      kicker: "Snapshot-Kontext",
      title: "Worauf diese Seite basiert",
      description:
        "Kurzer Kontext zu Aktualität, Stichprobengrösse, Abdeckung und den Grenzen des öffentlichen Exports.",
      sources: "Quellen",
      sourceTitle: (count) => `${count} öffentliche Jobportale`,
      sourcesDescription:
        "Vor der Veröffentlichung des Aggregats auf Stellenebene dedupliziert.",
      updated: "Aktualisiert",
      sampleSize: "Stichprobe",
      directEmployers: (count) =>
        `${count} direkte Arbeitgeber nach Filterung von Agenturen.`,
      salaryCoverage: "Gehaltsabdeckung",
      salaryCoverageDescription: (count) =>
        `${count} Inserate mit normalisierten CHF-Jahresgehaltsdaten.`,
      includes: "Snapshot umfasst",
      coreSignals: "Zentrale Marktsignale",
      limitations: "Wichtigste Grenzen",
      limitationsTitle: "Vor Zahlenvergleichen lesen",
      scopeItems: [
        "Stellenvolumen",
        "Gehaltsbenchmarks",
        "Rollen- und Senioritätsmix",
        "Nachfrage nach Stadt und Kanton",
        "Arbeitsmodell-Mix",
        "Skill- und Stack-Trends",
      ],
      limitationItems: [
        "Öffentlicher aggregierter Snapshot, keine vollständige Erhebung des Schweizer Marktes.",
        "Gehaltsbenchmarks nutzen nur Inserate mit expliziten Gehaltsspannen.",
        "Gehaltsrankings blenden Gruppen mit weniger als 10 nutzbaren Gehaltsdatensätzen aus.",
        "Die Abdeckung ist auf seit 2026 veröffentlichte Stellen beschränkt.",
        "Einige Felder werden normalisiert oder KI-gestützt aus Inseratetext und strukturierten Metadaten abgeleitet.",
      ],
    },
    findings: {
      kicker: "Zentrale Erkenntnisse",
      title: "Was aktuell auffällt",
      location: "Standort",
      locationTitle: (city) => `${city} hat den grössten Anteil`,
      locationDescription: (share) => `${share} der erfassten Stellen konzentrieren sich dort.`,
      momentum: "Dynamik",
      momentumTitle: (role) => `${role} wächst am schnellsten`,
      momentumDescription: (count, multiplier) =>
        `${count} Ausschreibungen in den letzten 30 Tagen, ${multiplier} gegenüber dem vorherigen 30-Tage-Fenster.`,
      compensation: "Vergütung",
      compensationTitle: "Gehaltsbenchmarks haben geringe Sicherheit",
      compensationDescription: (count, share, minCount) =>
        `${count} Inserate enthalten nutzbare Gehaltsdaten, das sind ${share} des Snapshots; Rankings blenden Gruppen unter ${minCount} Datensätzen aus.`,
      demand: "Nachfrage",
      demandTitle: (role) => `${role} bleibt der Nachfrageanker`,
      demandDescription: (share) => `${share} der erfassten Stellen fallen in diese Rollenkategorie.`,
    },
    summary: {
      vacanciesDescription:
        "Aktuelle Grösse des öffentlichen Exports im Schweizer Tech-Markt.",
      employersLabel: "Direkte Arbeitgeber",
      employersDescription:
        "Eindeutige einstellende Unternehmen nach Ausschluss von Recruiting-Agenturen.",
      publishedLabel: "In 30 T veröffentlicht",
      publishedDescription: "Neu veröffentlichte Stellen im letzten rollierenden Monat.",
      salaryCoverageDescription: (count) =>
        `${count} Stellen mit normalisierten Jahresgehaltsdaten.`,
    },
    charts: {
      mapTitlePrefix: "Schweizer",
      mapTitleAccent: "Stellenkarte",
      dashboardTitlePrefix: "Analyse",
      dashboardTitleAccent: "Dashboard",
      roleShare: "Anteil nach Rollenkategorie",
      leadingCantons: "Führende Kantone",
      workMode: "Verteilung nach Arbeitsmodell",
      seniorityMix: "Senioritätsmix",
      topCities: "Top-Städte",
      topEmployers: "Top direkte Arbeitgeber",
      topEmployersDescription: "Recruiting-Agenturen und Jobboards sind ausgeschlossen.",
    },
    salary: {
      sectionTitlePrefix: "Gehalts",
      sectionTitleSeparator: "",
      sectionTitleAccent: "metriken",
      snapshotTitle: "Vergütungs-Snapshot",
      snapshotDescription: "Vergleichbare CHF-Gehälter, auf Jahreswerte normalisiert.",
      breakdownAria: "Gehaltsaufschluss",
      roles: "Rollen",
      seniority: "Seniorität",
      averageYearly: "Durchschnitt pro Jahr",
      medianYearly: "Median pro Jahr",
      salaryCoverage: "Gehaltsabdeckung",
      records: "Datensätze",
      seniorityChartTitle: "Seniorität nach Durchschnittsgehalt",
      seniorityChartDescription:
        "Senioritätsstufen mit mindestens 10 normalisierten CHF-Gehaltsdatensätzen.",
      roleChartTitle: "Rollen nach Durchschnittsgehalt",
      roleChartDescription:
        "Rollenkategorien mit mindestens 10 normalisierten CHF-Gehaltsdatensätzen.",
      confidenceTitle: "Gehaltsbenchmark mit geringer Sicherheit",
      confidenceText: (minCount, hiddenCount, coverage, count) =>
        `Das Ranking zeigt nur Gruppen mit mindestens ${minCount} Gehaltsdatensätzen.${
          hiddenCount ? ` ${hiddenCount} Gruppen mit kleiner Stichprobe sind ausgeblendet.` : ""
        } Die gesamte Gehaltsabdeckung beträgt ${coverage} aus ${count} Datensätzen.`,
      median: "Median",
      noMetrics: "Keine vergleichbaren Gehaltsmetriken verfügbar.",
      salaries: "Gehälter",
    },
    skills: {
      sectionTitlePrefix: "Top",
      sectionTitleMiddle: "Skills",
      sectionTitleSuffix: "und",
      sectionTitleLast: "Kombinationen",
      topOverall: "Top-Skills gesamt",
      topOverallDescription: "Nach Häufigkeit in Stellenanzeigen sortiert.",
      skill: "Skill",
      vacancies: "Stellen",
      share: "Anteil",
      frequentPairings: "Häufige Kombinationen",
      frequentPairingsDescription: "Technologien, die oft gemeinsam genannt werden.",
      sharedVacancies: (count) => `${count} gemeinsame Stellen`,
      topLanguages: "Top-Programmiersprachen",
      topLanguagesDescription:
        "Sprach-Nennungen aus dem aktuellen Stellen-Snapshot.",
      coverage: "Abdeckung",
      distinctLanguages: "Unterschiedliche Sprachen",
      language: "Sprache",
      topFrameworks: "Top-Frameworks und Libraries",
      topFrameworksDescription:
        "Framework- und Library-Nennungen aus dem aktuellen Stellen-Snapshot.",
      distinctItems: "Unterschiedliche Einträge",
      frameworkLibrary: "Framework / Library",
      jobSkillsByRole: "Job-Skills nach Rolle",
      jobSkillsByRoleDescription:
        "Skill-Mix innerhalb der führenden Rollenkategorien. Segmentbreiten sind je Rolle normalisiert.",
      skillLegend: "Skill-Legende",
      skillsByRole: "Skills nach Rolle",
      noMatrix: "Keine Rollen-Skill-Matrix verfügbar.",
    },
    methodology: {
      sectionTitlePrefix: "Methodik",
      sectionTitleAccent: "lesen",
      sectionDescription:
        "Wie der öffentliche Snapshot zusammengestellt, normalisiert und für das Dashboard veröffentlicht wird.",
      pipelineTitle: "Pipeline-Überblick",
      pipelineDescription:
        "Das Dashboard basiert auf aggregierten Stellenexporten, KI-gestützter Stellenanreicherung und kompakten öffentlichen Snapshot-Dateien.",
      steps: [
        "Verarbeitete Stellenexporte aus der Multi-Source-Analytics-Pipeline sammeln.",
        "Unternehmen, Standorte, Arbeitsmodell, Seniorität und Gehaltsfelder deduplizieren und normalisieren.",
        "KI-gestützte Stellenanalyse ausführen, um Klassifikationen zu verbessern und Details zu erfassen, die regelbasierte Filter verpassen können.",
        "Gehaltsdaten vor der Aggregation in vergleichbare Jahreswerte in CHF umrechnen.",
        "Kompakte JSON-Snapshots und gespiegelte CSV-Exporte für das öffentliche Dashboard veröffentlichen.",
      ],
      coverageTitle: "Snapshot-Abdeckung",
      coverageDescription: "Build-Metadaten des Exports, der diese Seite speist.",
      generated: "Generiert",
      jsonSnapshots: "JSON-Snapshots",
      jsonDescription: "Öffentliche Dateien, die im Dashboard veröffentlicht werden.",
      csvInputs: "CSV-Eingaben",
      csvDescription: "Analytics-Exporte, die für diesen Build verfügbar sind.",
      missingInputs: "Fehlende Eingaben",
      downloadJson: "JSON-Snapshots herunterladen",
      downloadCsv: "CSV-Exporte herunterladen",
    },
    navigation: {
      ariaLabel: "Seitenabschnitte",
      title: "Navigation",
    },
    experience: {
      title: "Erfahrungsanforderungen",
      description: (minSize) =>
        `Explizit geforderte Jahre Berufserfahrung aus dem Inseratetext, gruppiert nach abgeleiteter Seniorität. Durchschnittswerte je Seniorität benötigen mindestens ${minSize} Jahresnennungen.`,
      seniorityMentionLabel: (count) => `${count} Jahresnennungen mit Seniorität`,
      yearsMentionedLabel: (count) => `${count} Nennungen von Berufsjahren`,
      averageMinimum: "Durchschnittlich mindestens",
      medianMinimum: "Median mindestens",
      mentionsBySeniority: "Erfahrungsnennungen nach Seniorität",
      seniority: "Seniorität",
      averageMinExperience: "Durchschn. min. Erf.",
      mentions: "Nennungen",
      distributionTitle: "Senioritätsverteilung",
      distributionDescription:
        "Gesamter abgeleiteter Senioritätsmix über alle Stellen, unabhängig von expliziten Erfahrungsnennungen.",
      vacancies: "Stellen",
      share: "Anteil",
    },
    trends: {
      kicker: "Index nach Veröffentlichungsdatum",
      title: (location) => `Stellenausschreibungen in ${location}`,
      description:
        "Trend nach Rollenkategorie mit Kantonsfiltern, abgeleiteten Schliessungen und Saisonalität.",
      filtersAria: "Filter für Stellentrends",
      region: "Region",
      switzerland: "Schweiz",
      professions: "Berufe",
      period: "Zeitraum",
      periodAria: "Zeitraum",
      granularityAria: "Granularität",
      days: "Tage",
      weeks: "Wochen",
      publishedSelection: "In Auswahl veröffentlicht",
      growthPrevious: "Wachstum ggü. Vorperiode",
      closedDisappeared: "Geschlossen / verschwunden",
      seasonalityHighLow: "Saisonalität hoch / tief",
      seasonalityHighLowWithMonth: (month) => `Saisonalität hoch / tief: ${month}`,
      legendAria: "Legende der Berufe",
      closedFootnote: "Geschlossen bedeutet: vor dem letzten Crawl zuletzt gesehen.",
      trendFootnote: "Der Trend nutzt Veröffentlichungsdaten der Stellen.",
      empty: "Keine Trenddaten für diese Auswahl.",
      chartTitle: "Stellentrend nach Beruf",
      tooltipTotal: (count) => `Total ${count}`,
      weekOf: (date) => `Woche ab ${date}`,
      monthNames: ["Jan", "Feb", "Mar", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"],
    },
    map: {
      emptyTitle: "Stellen nach Schweizer Stadt",
      emptyDescription: "Keine kartierbaren Schweizer Stadtmetriken verfügbar.",
      title: "Stellen nach Schweizer Stadt",
      description:
        "Rote Blasen sind nach Stellenzahl skaliert. Dunklere und grössere Blasen zeigen stärkere Konzentration in einer Stadt.",
      coverageDescription: (mapped, total, share) =>
        `${mapped} von ${total} erfassten Stellen sind auf der Stadtkarte platziert (${share} Abdeckung).`,
      summaryAria: "Zusammenfassung der kartierten Stellen",
      cities: (count) => `${count} Städte`,
      mappedVacancies: (count) => `${count} kartierte Stellen`,
      multiCity: (count) =>
        `${count} nennen mehrere Städte und werden auf Blasen aufgeteilt.`,
      broadLocation: (count) =>
        `${count} nutzen landesweite, regionale oder Remote-artige Standortangaben.`,
      unmapped: (unknown, unmatched) =>
        `${unknown} sind unbekannt und ${unmatched} weitere nutzen nicht kartierte Standortlabels.`,
      svgTitle: "Schweizer IT-Stellen nach Stadt",
      svgDescription:
        "Schweiz-Umriss mit roten transparenten Kreisen über Städten. Kreisgrösse und Deckkraft steigen mit der Stellenzahl.",
      markerTitle: (city, count) => `${city}: ${count} Stellen`,
      detailKicker: "Stadtdetail",
      selectCityTitle: "Stadtblase auswählen",
      selectCityDescription:
        "Klicke auf eine Blase in der Karte, um lokales Einstellungsvolumen, Marktanteil, Top-Rollen, Arbeitgeber und Arbeitsmodell-Mix zu sehen.",
      rank: (rank) => `#${rank} kartierte Stadt`,
      vacancies: "Stellen",
      marketShare: "Marktanteil",
      topRoles: "Top-Rollen",
      noRoles: "Kein Rollenaufschluss verfügbar.",
      topEmployers: "Top-Arbeitgeber",
      noEmployers: "Kein Arbeitgeberaufschluss verfügbar.",
      workMode: "Arbeitsmodell-Mix",
      noWorkMode: "Kein Arbeitsmodellaufschluss verfügbar.",
      chooseCity: "Andere Stadt auswählen",
      searchHelp: "Tippen zum Suchen oder Pfeiltasten nutzen.",
      searchPlaceholder: "Stadt suchen",
      noCity: "Keine passende Stadt gefunden.",
    },
  },
};

export function normalizeLanguage(value) {
  const normalizedValue = String(value ?? "").toLocaleLowerCase("en-US").slice(0, 2);
  return LANGUAGE_OPTIONS.some((option) => option.code === normalizedValue)
    ? normalizedValue
    : null;
}

export function getCopy(language) {
  return LANGUAGE_COPY[normalizeLanguage(language) ?? DEFAULT_LANGUAGE];
}

export function getLocale(language) {
  return LANGUAGE_LOCALES[normalizeLanguage(language) ?? DEFAULT_LANGUAGE];
}

export function getInitialLanguage() {
  if (typeof window === "undefined") {
    return DEFAULT_LANGUAGE;
  }

  const searchLanguage = normalizeLanguage(new URLSearchParams(window.location.search).get("lang"));
  if (searchLanguage) {
    return searchLanguage;
  }

  const savedLanguage = normalizeLanguage(window.localStorage.getItem("swiss-it-jobs-language"));
  if (savedLanguage) {
    return savedLanguage;
  }

  return normalizeLanguage(window.navigator.language) ?? DEFAULT_LANGUAGE;
}
