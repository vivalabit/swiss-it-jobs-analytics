# Swiss IT Jobs Analytics

Swiss IT Jobs Analytics is a tool that analyzes thousands of job postings across the Swiss market to identify the most in-demand skills, technologies, and career paths, helping you understand what to learn today to stay competitive tomorrow.

See right now - https://vivalabit.github.io/swiss-it-jobs-analytics/

Current sources:

- `LinkedIn`
- `jobs.ch`
- `jobscout24.ch`
- `jobup.ch`
- `swissdevjobs.ch`

The dataset is deduplicated across sources at the vacancy level.
When the same job is posted on multiple job boards, it is counted once in the public statistics.

The project is still in progress, so statistics and structure may change.

The public site publishes aggregated snapshots of the Swiss IT job market built from processed vacancy datasets across multiple job boards. It highlights broad signals such as vacancy volume, employer activity, skill demand, salary ranges, geographic concentration, seniority mix, and work mode distribution.


## What This Project Covers

This project is designed to answer practical, data-driven questions about the job market:

- Which roles are currently the most in demand
- Which skills and technologies appear most frequently
- Which cantons and cities have the highest concentration of job postings
- How demand is distributed across seniority levels
- How comparable salary ranges differ across role categories
- Which skills the market is actually valued by employers

**The statistics cover vacancies published from 2026 onward.** 
**Staffing agencies are excluded**

## Metodology

We collect job postings from several sources (LinkedIn, jobs.ch, jobscout24.ch, jobup.ch, swissdevjobs.ch), store them in local SQLite databases for each provider, then map them to a common schema and generate aggregated statistics based on the combined dataset. During the consolidation phase, we use deduplication based on job identity within each source to prevent duplicate imports from inflating the statistics.

Next, each job posting is normalized: the company, location, canton, seniority, work mode, and salary fields are standardized, while role category, skills, programming languages, frameworks/libraries, and other analytical attributes are extracted from the text and structured fields. Salaries, if available, are converted to a comparable annual format in CHF so that we can calculate summaries and breakdowns by role and seniority.

After that, agencies and recruitment intermediaries are excluded from the overall sample. This is important: in our public statistics, we strive to track the direct job market specifically, rather than the activity of intermediaries, who may repost similar positions multiple times and distort the picture of demand. Exceptions are made based on a normalized list of known staffing/recruitment companies and their aliases.

Job vacancies are further analysed using AI: standard software filters often fail to recognise all the relevant information and may overlook important details. AI does not replace these filters or invent data, but works alongside them to provide a more in-depth and accurate analysis.