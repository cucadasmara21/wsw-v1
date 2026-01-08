# WallStreetWar — Technical Whitepaper

This document describes the architecture, data model, quantitative algorithms, information flows, and implementation roadmap of the WallStreetWar system. It is intended as a technical reference for developers, quants, risk managers, and institutional stakeholders.

## 1. System Vision and Purpose
The global financial system is highly interconnected... (full text below)

### Executive Summary
WallStreetWar is designed to answer the question: Where is structural fragility accumulating, and how might a local shock propagate to the rest of the system? It is not a trading platform, but a systemic risk intelligence engine that combines:
- Comprehensive ontology of the financial system
- Causal network architecture (relationship graph)
- Explainable quantitative algorithms (risk vectors, HMMs, copulas, propagation engine)

## 2. Functional Scope for the End User
(The key questions and main functionalities described in the original document are maintained)

- Questions the engine must answer (e.g., hotspots, contagion routes, 50–100 highest-impact assets, explanations for alerts)
- MVP functionalities: hierarchical map, continuous ingestion, recurrent calculation of risk vectors and CRI, network and SIS metrics, propagation engine, explainable alerts, dashboard, and APIs for different roles.

## 3. Ontology and Data Model
### 3.1 Hierarchical Levels
Group → Subgroup → Category → Asset. Each asset belongs to a unique category that inherits higher-level metadata.

### 3.2 Cross-Functional Relationships
Key relationships: IS_ISSUED_BY, USES_COLLATERAL, DERIVES_FROM, HOLDS_EXPOSURE_TO, HEDGED_WITH. Represented in Neo4j as edges with properties (weight, lag, type).

### 3.3 Logical Schema in Neo4j
Labels: Group, Subgroup, Category, Asset, Issuer, Fund, Bank, Index, ETF. Idempotent loading with MERGE and configuration CSVs.

## 4. General Software Architecture
### 4.1 Logical Layers
1) Ingestion and Normalization
2) Dual Storage: TimescaleDB (time series) + Neo4j (topology)
3) Analysis and Risk: Python microservices
4) Service and Presentation: REST/GraphQL API + dashboard

### 4.2 Data Flows
1) Raw Ingestion → 2) Normalization (UTC, currencies) → 3) Enrichment (map to Asset) → 4) Persistence (TimescaleDB hypertables) → 5) Risk Calculation → 6) Signal Generation → 7) Exposure in the API/UI

### 4.3 Performance and Costs
Initially focused on open-source and single-node software; partitioning and compute frequency decisions aimed at balancing cost and realism.

## 5. Risk Vector and Quantitative Metrics
- Vector R_a(t) = (R^price, R^fund, R^liq, R^cp, R^regime)
- Indicators: 30/90d volatility, drawdowns, gaps, relative volume, financial ratios, collateral quality, concentration metrics.

- CRI: normalized weighted linear combination on a scale of 0–100 (thresholds: >80 red, 60–80 amber).

- SIS: based on network metrics (betweenness, eigenvector, closeness) and connectivity to critical nodes.

## 6. Regime, Causality, and Dependency Models
- HMMs for regimes (Normal, Stress, Panic)
- Granger causality for lead-lag (directed edges with lag_days)
- Copulas (t, Archimedean) for nonlinear dependencies between assets and across different regimes

## 7. Stress Propagation Engine
- Model: graph G = (V,E), shock s_0 → iterations s_{k+1} = γ W^T s_k or cumulative BFS/DFS in MVP.

- Initial implementation in BFS/DFS with queuing and propagation threshold; results stored per scenario in TimescaleDB.

- Scenarios: observed (real movements) and hypothetical (user-defined)

## 8. Explainable Alert System
- Types: EW (Early Warning), BA (Break Alerts), SNA (Systemic Node Alerts), PLA (Portfolio-Linked Alerts)
- Engine: deterministic rules + percentile-based triggers; parameter versioning and full traceability.

## 9. User Interface, Flows, and Roles
- Flows: heatmap → zoom → node → neighborhood → alerts → simulate scenario
- Roles: Standard, Pro, Institutional/Regulatory. Different permissions and views.

## 10. Technology Stack and Deployment
- Docker/Docker Compose for single-node deployments; Kubernetes for future scalability
- PostgreSQL + TimescaleDB, Neo4j Community, optional Redis, FastAPI backend, React/Next.js frontend
- Integrations: market data providers, macro APIs, messaging (email/webhooks)

## 11. Data Quality, Governance, and Auditing
- Validations in each pipeline, quality metrics per source
- Versioning of models and parameters; all calculations and alerts reference version identifiers
- Structured logging with correlation IDs; ELK/Loki+Grafana stack for research

## 12. Use Cases (examples)
- CRE/MBS case → EW detected, critical nodes, vulnerable regional banks
- Stablecoin case → peg deviation, routes to traditional assets
- LDI funds case → presidentOn the curve, high SIS, simulated impact

## 13. Implementation Roadmap
- Sprint 1 – Foundations (containers, Neo4j, TimescaleDB, ontology)
- Sprint 2 – Historical ingestion and pipelines
- Sprint 3 – Vector calculation and CRI
- Sprint 4 – Network metrics and SIS
- Sprint 5 – Propagation and scenarios
- Sprint 6 – Alerts and dashboard
- Subsequent Sprints – Portfolios, institutional APIs, cloud deployment, and hardening

## 14. Conclusion
WallStreetWar offers an explainable, scalable, and verifiable approach to systemic risk monitoring. This document serves as a technical guide for development and stakeholder discussions.

--

If you'd like, I can:
- Divide this white paper into a `docs/` folder with sections and generate a table of contents.

- Create issues or a checklist for each sprint (Roadmap → issues).

- Generate diagrams (architecture, data flow, propagation model) and add them to the repository.

Which would you prefer I do next?
Technical Report: Engine Backend
WallStreetWar
Proposed Backend Technologies
The technical whitepaper describes a technology stack based on open-source tools and Docker containers. The main components include:

• Orchestration: Docker and Docker Compose to deploy services on a single node initially; and Kubernetes planned for future horizontal scaling.

• Data storage: PostgreSQL with the TimescaleDB extension to store time series (market data, historical metrics) and Neo4j Community to persist the graph of financial relationships. Redis is optionally considered as an in-memory cache for recent signals/alerts.

• Backend: Microservices in Python (FastAPI framework) implementing data ingestion, risk calculation, stress propagation, the alerting system, and API exposure.

• Frontend: A web dashboard; In prototypes, Streamlit is suggested, later evolving to

React/Next.js (TypeScript) for the user interface.
4. The frontend will connect to the backend
via REST API or GraphQL.

• External integrations: Connectors to obtain data from market providers, macroeconomic APIs,

news/event feeds, and messaging systems for notifications

(email, webhooks).

Comment: All these technologies are explicitly mentioned in the document, providing a clear
guide to the stack. No additional languages ​​besides Python/TypeScript are cited, so it can be inferred that

Python dominates the server layer (backend) and TypeScript/JS the client layer. The use of open-source software (e.g.,
TimescaleDB, Neo4j) indicates a preference for minimizing licensing costs.

General Architecture and System Layers
The backend is structured in four well-defined logical layers, which can initially coexist on a single server and later be distributed. According to the whitepaper, these layers are:

• 1) Ingestion and Normalization Layer: Obtains data from multiple external sources, performs cleaning and validation, normalizes formats/timestamps, and enriches each data point with ontology metadata (mapping the ticker or ID to the asset and its corresponding category).

• 2) Dual Storage Layer: Persists the processed data in two specialized stores – TimescaleDB for time series prices/indicators, and Neo4j for the system topology (graph of relationships between assets, entities, and financial vehicles).

This separation allows for efficient querying of both historical data and the network of interdependencies.

• 3) Analysis and Risk Layer: A set of Python microservices that calculate quantitative metrics. Here, risk vectors per asset, composite indices, and network metrics (centralities, communities) are generated, and algorithms such as regime models or stress propagation simulations are executed.

1

• 4) Service and Presentation Layer: Exposes the results through a REST/GraphQL API and provides a web dashboard for human consumption (analysts, managers) or automated consumption (institutional integrations). This layer provides the endpoints that allow users to query the risk heat map, network graphs, alerts, etc., ensuring that the other layers can be easily leveraged.

Figure – Architecture diagram of the WallStreetWar system, showing the data ingestion layer (left), normalization and storage layer (center), risk analytics engine (bottom), and the service/API layer + dashboard (right). The document also illustrates the data flow from external sources, through validation,
metric calculation (risk vectors, indices, regime detection, stress propagation), to
alert generation and their exposure via API.

In the initial phase, the entire architecture can be deployed on a single machine with multiple
Docker containers communicating on a common internal network.<sup>10</sup> This simplifies early development, although it means that all services (Timescale DB, Neo4j, API, etc.) reside on the same
host. As the load grows (more data or concurrent users), the document proposes migrating
to the cloud and separating critical components: for example, using a managed TimescaleDB, Neo4j on its own instance, and scaling the backend behind a load balancer.<sup>11</sup> In other words, the architecture is designed to scale horizontally in the future, transforming the layers into distributed services (e.g., deploying microservices on Kubernetes and dedicated databases).

Comment: The backend architecture is clearly and explicitly described in the document, including the function of each layer. However, the specific implementation details are not detailed.
(For example,
how the microservices will communicate internally with each other or with the databases) are not
explored in depth; the use of direct database calls or internal APIs is assumed, but an
explicit messaging bus is not mentioned. A diagram is also not provided in the PDF, although the
project includes one (as shown above). Even so, the layering and its purpose are
well defined, providing a solid foundation for designing the backend.

Microservices Structure and Functional Modules
The WallStreetWar backend follows a microservices approach where different key functionalities
are implemented as separate Python services (using FastAPI). The whitepaper
explicitly mentions several functional modules that the backend should cover, aligned with the

2
MVP functionalities described for users 12 and 13. These main modules/services include:

• Data Ingestion: A service responsible for connecting to external sources (markets, financial data feeds, macro APIs, etc.), downloading or receiving raw data, and processing it for cleaning and normalization. This module integrates schema and data quality validations (e.g., format checks, valid ranges, timestamps) before accepting the information.

• Enrichment and Ontology: As part of ingestion, there is a component that maps each data point to an asset defined in the internal ontology. This involves translating external identifiers (ticker, ISIN, etc.) to the asset's internal ID and attaching its corresponding category, subgroup, and group.

This enrichment ensures that all data is structured according to the defined hierarchy (allowing consistent aggregations by subgroup, group, region, etc.). • Risk vector and index calculation: Dedicated microservices for analytical processing
that transform stored data into risk metrics. These processes can be batch
or streaming, and periodically calculate the risk vector for each asset, its components, and the aggregated
Composite Risk Index (CRI). They also compute network metrics (centralities,
community detection) and the Systemic Influence Score (SIS) for each node in the graph,

using data from Neo4j.

• Stress propagation engine (scenario simulation): A service that takes events

(observed or hypothetical) and simulates how a financial shock propagates through the network of
assets/entities. In the first version, the document proposes implementing this engine with a
simple breadth-first/depth-first search (BFS/DFS) algorithm, accumulating stress along
the relationships in the graph. This module must accept two types of scenarios: observed

(e.g., when an asset experiences an actual anomalous movement) and hypothetical scenarios defined by the
user (e.g., “What happens if market X falls by 10%?”) 19. The results of each simulation
could also be saved in the database (e.g., in TimescaleDB indexed by timestamp and
scenario tag).

• Explainable alert system: A microservice that continuously monitors the calculated
risk metrics and applies a rules engine to generate alerts when it detects anomalous
conditions 20. The alerts are classified by type (Early Warnings, Stress Alerts, etc.)

according to the magnitude and nature of the event 21. This module combines deterministic rules

(fixed thresholds) with statistical triggers based on historical percentiles. For example,

an Early Warning alert could be triggered if the average CRI of a subgroup rises >30% in 10 days,

or if an asset enters the red zone (CRI>80) consistently.<sup>21</sup> Each generated alert includes an

explanation: relevant metrics (e.g., asset CRI and SIS, recent changes), the path or causal factors
that contributed to the alert, and even links to graphs or the involved subgraph.<sup>22</sup>

Furthermore, the alerting system stores each event in an audit table with a timestamp
and version of the model/rules used, facilitating traceability and forensic analysis afterward.<sup>22</sup>

• Data exposure via API: While each microservice performs specific calculations, the
results need to be accessible to the interface and other clients. To achieve this, the backend exposes
centralized API endpoints (REST/GraphQL), either by aggregating the different services under a single
gateway or by having certain microservices offer their own endpoints. The document indicates that institutional users will be able to access the information via APIs,

not only via dashboard 23, therefore the architecture must support automated queries Direct links to risk data, alerts, and simulations.

Comment: The document explicitly outlines several of these modules (ingestion, risk calculation, stress testing, alerts) and their general implementation, even indicating that FastAPI and Python will be used for each microservice.

However, the interface between microservices is not detailed (for example, whether they will communicate via internal HTTP calls, Kafka-like message queues, or other mechanisms).
Since the possibility of using Kafka for data sources is mentioned in the diagram (suggesting real-time feeds), it could be inferred that an event queue will be used in the future, but the whitepaper does not explicitly discuss this. In practice, developing these microservices will require defining how to orchestrate them: initially, they could share the database as an integration point (each service writes to/reads from TimescaleDB/Neo4j according to its function), while the central API reads from these databases to serve the frontend.

REST/GraphQL API and Endpoints
The service layer exposes a web API that allows both the user interface and external clients to query the engine's analytical data. The whitepaper indicates that this API will support REST and/or GraphQL styles, providing flexibility in how data is obtained. In practice, this means that endpoints will be implemented to obtain:

• Hierarchical data from the system map (lists of groups, subgroups, categories, assets),

• Current and historical values ​​of risk vectors and composite indices per asset or by aggregations (subgroup, group),

• Network metrics (e.g., centralities, communities, SIS of each node),

• Results of stress simulations (run scenarios and their impacts),

• Active alerts or alert history, with explanatory details.

The document does not explicitly list each endpoint or the URL scheme, leaving a gap to be defined in the implementation. However, it is clear that the web dashboard will consume this
API to build visualizations (risk heatmaps, graph views, event timelines).

24 Additionally, it is mentioned that certain (institutional) users will have direct access to the

API to integrate it with their systems, 23 which implies that robust authentication mechanisms (tokens/API keys) and role-based access control on the endpoints must be considered.

It is also envisioned to offer an optional or complementary GraphQL endpoint, which would allow for more specific and optimized queries (for example, requesting in a single query the n assets with the highest
SIS along with their recent metrics). Again, the whitepaper does not detail how the
GraphQL schema would be structured, but its mere mention suggests that the backend design must consider this
technical possibility. In fact, it is indicated that a modern frontend (React/TypeScript) could connect
via GraphQL to the microservices, which usually implies the existence of a unified GraphQL server
on top of the business logic.

Comment: The presence of an API is clearly specified, but not its details. It is not mentioned, for example, whether there will be API versioning (v1, v2), nor are there any examples of calls. This means that
during development, the endpoints will need to be designed following REST best practices (resources such as

/api/asset/{id}/risk, etc.) or a GraphQL schema will need to be implemented with types that reflect the objects
in the domain (Asset, RiskVector, Alert, ScenarioResult, etc.). The development team will also need to
decide whether to use a single FastAPI service as a unified API gateway or if each microservice will expose
its own endpoints and an API Gateway will be used to aggregate them. In any case, the security and efficiency of these endpoints will be critical given the requirement for fast UI responses (ideally sub-second for typical queries).

4. Security and Authentication
The document emphasizes that the platform must be secure, with robust authentication and data segregation between users. Since three user roles are identified (Advanced Retail, Professional, Institutional/Regulatory), the backend layer must implement an authentication and access control system that ensures each user can only see the views or data authorized for their role. For example, a standard user might have limited access to certain aggregated data, while an institutional user might have access to more detailed data or advanced functionalities (such as the full API, custom scenarios, etc.).

While the whitepaper doesn't explicitly mention mechanisms like JWT, OAuth2, or encryption,
the context suggests that authentication will likely be performed using secure tokens (JWT) or a secure session system provided by FastAPI. This perThis would allow the issuance of access tokens
for the APIs, including scopes or claims that indicate the user's role (so that the backend
can filter the information appropriately). “Data separation between users” suggests that if the platform supports multiple clients or multi-tenant instances in the future, sensitive data will need to be isolated (for example, private scenarios of an institutional client should not be visible to
others).

Regarding authorization, roles will need to be mapped to specific permissions in the application. The
document already suggests differences in capabilities: a Pro User can export data and configure
rules, while an Institutional User can have on-premises integration and full API access. Implementing this could involve middleware in the API to verify permissions on each
request.

Another security aspect not detailed in the document is API protection against abuse: rate limiting, strict input validation (given that external data is ingested, preventing SQL/Neo4j injections, and sanitizing input) and using HTTPS for API traffic should all be considered. The whitepaper also doesn't explicitly mention credential or secret management (e.g., API keys from data providers), but since it's a financial system, this should be handled with secure practices (configuration files outside the repository, vaults, etc.). In short, although the need for security is explicitly mentioned in terms of objectives 26, it's up to the development team to define and implement the details (JWT/OAuth, encryption of sensitive data, security logs, etc.).

Persistence and Database Connection
The proposed solution uses a dual storage strategy to leverage different databases depending on the type of information:

• TimescaleDB (PostgreSQL): stores all time series of financial data, indicators, and historical results.<sup>6</sup> TimescaleDB, being a PostgreSQL extension optimized for time series, allows for the efficient handling of large volumes of chronological data with automatic partitioning (hypertables). The document mentions that the data is inserted into optimized hypertables and that certain aggregates could be automatically recalculated (using continuous aggregates).<sup>28</sup> Data partitioning decisions (e.g., defining hypertables by individual asset or by group) are also discussed as part of performance tuning.<sup>29</sup> In implementation, this involves designing a relational schema where each asset has its associated tables of metrics, indexes, etc., possibly using partitions by date ranges or categories to accelerate queries.

5

• Neo4j: stores the graph topology of the financial system, that is, the nodes that
represent assets or entities and the relationships between them. 6. The ontology defined in the
system includes nodes of type Group, Subgroup, Category, Asset, Issuer, Fund, Bank, Index, ETF,

connected by relationships such as HAS_ASSET, IS_ISSUED_BY, USES_COLLATERAL, DERIVES_FROM,

HOLDS_EXPOSURE_TO, HEDGED_WITH, etc. 30 31. Each edge in Neo4j carries properties (weight,
direction, time lag, type) to model financial dependencies in detail. 32. The
choice of Neo4j allows executing graph queries (e.g., finding contagion paths,
calculating centrality) directly on the defined relationships, something difficult to achieve
efficiently with pure SQL. The initialization of this graph would be done using idempotent scripts that load the base ontology (the ~20 groups, their subgroups, categories, and assets) from CSV configuration files.

Both databases are initially planned as local Docker containers (using images of Neo4j Community and Postgres/Timescale). The backend connection to the databases would typically be done using the official drivers (e.g., the Python driver psycopg2 or SQLAlchemy for PostgreSQL/Timescale, and the Bolt driver neo4j-python-driver or an ORM like Neomodel for Neo4j). These details are not explored in the document, but they have practical implications: Python microservices will need to connect to TimescaleDB to read/write series (for example, the ingestion layer will insert calculated prices and metrics), and connect to Neo4j to query or update relationships (for example, the stress engine could add temporal contagion relationships, or the alerting system could query a node's exposure network).

In addition to TimescaleDB and Neo4j, the stack optionally includes Redis. Although its use is not detailed, it is reasonable to assume that Redis would be used to cache recent or frequently occurring results (for example, the latest risk heat map, or the most recent alerts) to accelerate responses to the dashboard without hitting the database on every request. It could also be used for simple pub/sub queues to notify the UI of alert events in real time.

Regarding integrity and consistency between databases, the document doesn't go into detail. Ensuring synchronization will be important during implementation: for example, if a new asset is added to the ontology (Neo4j), its corresponding time series should also be configured in Timescale. The design suggests that Timescale and Neo4j are complementary sources of truth (Timescale for quantitative metrics, Neo4j for relationships), so the microservices will act as a bridge between them (enriching data with graph IDs, or storing analytical results with cross-references).

Finally, in a scaled production scenario, migration to managed instances is likely: TimescaleDB Cloud or a scalable Postgres, and a dedicated Neo4j 11 cluster. This
implies that the architecture must facilitate the reconfiguration of connections (for example, using
environment variables for connection strings) and consider migration/backup tools for
both databases.

Comment: The choice of TimescaleDB and Neo4j is clearly specified in the whitepaper, as is
their respective purpose.<sup>6</sup> Certain technical details are also mentioned (optimized hypertables, etc.), which demonstrates explicit planning of the data schema. However,
practical aspects remain unaddressed, such as the sharding strategy or specific indexes in the time database,
or how long-term graph maintainability will be handled. There is also no mention of
managing a data warehouse or repository of long historical data outside of Timescale (although
Timescale can handle it, old data is sometimes archived). These decisions will have to be made by the
technical team as needs and volumes evolve.

6
Analytical Engine and Risk Calculation Logic
The “systemic risk intelligence engine” implemented in the backend is the analytical core of
WallStreetWar. The document details the quantitative calculations this engine must perform,
providing a theoretical basis for its implementation. Its main components and logic are summarized below, indicating what is explicitly stated in the white paper:

• Risk vector per asset: For each asset at time t, a multidimensional risk vector Ra(t) is defined with five main components: price risk, fundamental risk, liquidity risk, counterparty risk, and market regime risk. Each component, in turn, is derived from several specific indicators. For example, price risk includes metrics such as 30/90-day realized volatility, recent maximum drawdown, price gap frequency, return skewness/kurtosis, etc. Liquidity risk may include average volume relative to the
historical median, bid-ask spread width, percentage of days without trading,
volume concentration among a few participants, etc. 35. Fundamental risk (for corporate
assets) derives from financial ratios such as Debt/EBITDA, interest coverage,
margins, and asset quality; while for structured vehicles it is based on the quality
of collateral, triggers, overcollateralization levels, ratings, etc. 36. Counterparty risk
is estimated based on the credit quality of issuers, concentration of brokers/clearing houses, and
dependence on volatile collateral. 37. Each gross indicator is normalized (using Z-scores,
percentiles, or robust scaling) and then transformed to a unified scale of 0 to 100. 38. This
means that the backend will need to implement statistical calculation routines for each asset,

integrating data from different sources (market prices for volatility, financial data

for ratios, etc.) and applying standard transformations. Many of these metrics will be

recalculated recurringly (daily or weekly) using the analytics microservices.

• Composite Risk Index (CRI): This is a one-dimensional aggregate of the risk vector. The CRI

of an asset is obtained as a weighted combination of its five normalized

components. The weights can vary depending on the asset type (for example, liquidity might

weigh more heavily on illiquid assets, fundamentals more heavily on credit, etc.) and are calibrated through

backtesting and expert judgment. A high CRI indicates an asset in a risk zone: the document

suggests that a CRI > 80 is considered a “red zone” (very high risk) and 60–80 an “amber zone” (monitoring). This interpretation scheme is explicitly mentioned, which

implies that the backend must maintain these configurable thresholds and possibly a adjustable
over time. It also mentions that the weights are reviewed periodically, which implies that the
implementation must support parameter versioning (as discussed in section 11.2
of the document, each model or weight change must be recorded with a version ID 41).

• Network and Systemic Influence (SIS) Metrics: Beyond individual risk, the system calculates the
importance of each node in the financial network. The Systemic Influence Score (SIS) is based on
classic graph metrics (centrality, betweenness, eigenvector, closeness, etc.)

combined with connectivity to pre-identified critical nodes (e.g., large systemic banks, key collateral markets, giant ETFs) 17. Essentially, SIS measures how
“connected and indispensable” an asset is within the network: a high value would indicate that
disturbances at that node could have a broad effect on the system. The SIS is calculated both at a global level across the entire graph and within each community or group to detect local vs. global hubs. To implement this, the backend will need to query the graph in Neo4j – possibly using Neo4j's built-in algorithms (such as PageRank and centrality algorithms) or by exporting the adjacency matrix to Python for custom calculations. Since the SIS combines multiple factors, the final calculation would be expected to be a weighted aggregation of several metrics, the exact weights and formula of which could be adjusted with calibration (the document does not provide an explicit formula, leaving it conceptual).

• Market regime models: The document dedicates section 6 to additional quantitative models. In particular, Hidden Markov Models (HMMs) will be used to classify each market day into one of several regimes: for example, “Normal,” “High Volatility,” “Stress/Liquidation,” or others. This market regime classification feeds one of the
risk vector components (the Rregime component). Implementing it will involve the
backend periodically running an HMM model (possibly pre-trained or continuously calibrated
) on relevant time series (e.g., broad indices, or the composite
indices themselves) to determine the market state. Also mentioned is the use of Granger causality tests
for detecting lead-lag relationships between assets 44, and copulas
for modeling nonlinear dependencies between assets (e.g., between safe-haven and risk assets) 45. These elements suggest that the backend will include a sophisticated
quantitative component, likely implemented in Python with statistical libraries (e.g., hmmlearn
or similar for HMM, statsmodels for Granger, copula libraries). Although explicitly mentioned
in the document, the precise mathematical details are left to the implementation; For example, it will be necessary to decide the frequency of regime recalculation (daily, weekly) or how to store the results (possibly as part of the risk vector in TimescaleDB).

• Stress propagation engine (contagion simulator): Chapter 7 of the white paper describes how shock simulation will be approached in the network. Conceptually, the financial network is represented as a directed graph G=(V,E) where the nodes V are assets/entities and the edges E represent dependency or exposure relationships. If an initial shock is applied to one or more nodes (e.g., a 30% drop in the price of an asset, or a default by an issuer), the engine traverses the graph propagating that stress according to the relationships (for example, a bank suffers losses if an asset to which it is exposed collapses, etc.). In the MVP, the simulation is simplified

with a BFS/DFS propagation algorithm: a queue is initialized with the source nodes and their
stress level, then the stress is iteratively passed to their neighbors along the edges and
attenuated according to the weight/lag of each relationship. This deterministic approach allows
it to efficiently determine which second- and third-order nodes would be affected by the initial shock.

The system must support triggering this engine in two cases: automatically for
observed events (when it detects, for example, that an asset experienced extreme movement,
it could simulate the consequences) and for hypothetical scenarios defined by the user.

For advanced users, there will be an interface where they can input a custom "shock" (e.g., X% drop in a certain asset, or a change in a macro variable), and the backend
will run the propagation in the graph, returning the results (possibly a list of impacted nodes
with their resulting stress levels). The document suggests storing the
scenario results in the database with an identifier and timestamp 47, which
would allow for scenario comparisons and even visual comparisonsTo optimize propagation on the dashboard. In
future implementations, mentioned in the roadmap section, more
realism could be incorporated into this engine (for example, incorporating nonlinear feedback or Monte Carlo simulations), but the initial version prioritizes simplicity and explanatory power.

• Alert generation and explainability: After calculating risk metrics and simulating events,
the backend generates signals and alerts that notify of emerging risks. The alerting logic
combines predefined conditions with statistical results. For example, the document
mentions Early Warning alerts, likely triggered when a
market segment shows significant deterioration (CRI or metrics rising rapidly).

21 Other alerts could indicate Stress Alert (when a propagating shock affects many

nodes) or Regime Shift (a sudden change in the market regime). Each alert includes

8
contextual information to make it explainable: this is achieved by attaching the values ​​of the
main variables that led to the alert (e.g., “CRI of asset X rose from 50 to 85 in 2 weeks;

SIS in the top 5%; volatility doubled”) and references to causal relationships in the graph (e.g., “asset X is linked to asset Y, which is also in the red zone”) 22. This explanation is built
from the data available in the ontology and the time series, so the backend
must compose messages from queries to both TimescaleDB (numerical values) and

Neo4j (relevant neighbors, paths in the graph). Furthermore, each alert issued is saved with
a unique identifier, timestamp, and the current model/rules version 22, which allows for
auditing: that is, the ability to later reconstruct why the alert occurred (with what thresholds,

what inputs). This ties into the data governance and auditing section (section 11 of the document),

which emphasizes the importance of logging each process with correlation IDs and maintaining
version control of all models and parameters for traceability.<sup>41,48</sup> In practical terms,

this means that backend development must include a robust logging and metadata storage system
for each calculation/alert. A database or index (e.g., in Elasticsearch or Timescale itself) may be implemented where each alert and each calculation run is recorded
with its parameters.

Comment: The risk engine logic is explicitly and thoroughly described in the document, covering the main algorithms and indicators. This provides a clear roadmap of what needs to be implemented
in analytical terms. However, no exact formulas or code are provided,
so there are areas where the developer will need to make decisions: for example, choosing
libraries or methods to calculate HMMs or copulas, deciding on initial alert thresholds, and optimizing
computation speed (perhaps by precomputing some things). Also, although the theory behind the calculations
is there, the sequence will need to be orchestrated: ingestion feeds the risk calculations (perhaps at the end of
each day or in intraday streaming), then composite indices are updated, then graph centralities are recalculated, and so on, and finally alert rules are run. These timing dependencies are not
explicitly stated in the text, but the team will need to design the appropriate pipelines (possibly using
an internal scheduler or cron job, mentioned in the diagram as a Scheduler component within
"Governance and Admin"). In short, the document defines what to calculate, but how and when
to integrate it into sequential processes is part of the implementation.

Data Flow from External Sources to the Analytical Engine
The white paper describes a typical seven-step data flow from raw data acquisition to alert generation and visualization:

1. Raw Data Ingestion: The system receives or downloads data from various external sources, including market prices, volumes, fundamental company data, macroeconomic indicators, and news/structural events. This can occur in (near) real-time via APIs and feeds, or in periodic batches (e.g., daily).

2. Normalization: The raw data is standardized in terms of format and timing. The timestamp is verified and standardized (converting it to UTC, for example), units and formats are checked (e.g., decimal points, separators), and missing data is handled (filling in gaps or deleting them as needed). Currencies are also unified to a common base

where applicable. This stage ensures that, regardless of the source, the data enters the system with a consistent structure.

3. Enrichment with ontology:Each data record is mapped to an element of the internal ontology.

That is, using identifiers such as ticker, ISIN, or name, the system determines which specific asset it corresponds to and appends its metadata (category, subgroup, group, region, etc.).

This step allows individual data to be immediately aggregated hierarchically: for example, if a new piece of data, “Price of Bond X,” is entered, the system knows which category (e.g., Corporate Bonds) and subgroup (Credit) it belongs to, and can then calculate averages or indices at the level of those groupings.

4. Persistence in databases: After cleaning and enriching, the data is stored permanently.

Numerical values ​​in time series (prices, indices, calculated metrics) are inserted into TimescaleDB in specialized tables (hypertables) optimized for time-series queries.

49 In parallel, if the data implies a new relationship or entity (less frequent, since the ontology is relatively static), Neo4j would be updated. Additionally, some aggregates or summaries could be calculated at this point (for example, Timescale allows defining continuous aggregates to keep the moving average of certain indicators ready).
5. Calculation of risk metrics: Batch or streaming processes consume the newly stored data to update the analytical metrics. This includes recalculating the risk vector of each asset with the most recent data, updating the CRI, recalculating the SIS and other network metrics if relevant data has changed, and running regime, causality, or dependency models on the updated series. This step represents the analytical core: it can be scheduled to occur, for example, every night with market closing data, or continuously as new data arrives (for streaming data). In the first version, it could run as sequential jobs (first asset calculations, then network calculations, then regime calculations, etc.) since everything will reside on a single server.

6. Signal and alert generation: The metric results feed the alert rules engine. Here, defined rules (e.g., “CRI > 80” or “volatility jump of X standard deviations”) and detection models look at the calculated risk and event series to trigger alerts when anomalous conditions are met. Each alert is accompanied by its explanation (as detailed earlier) and a severity level. At this stage, the system may also notify subscribed users (via email or webhook) if the alert is critical, which connects to the external integration layer (message sending). 7. Dashboard/API Presentation: Finally, the frontend (web dashboard) queries the backend API
to obtain the processed data and display it to the user. For example, when a user opens the heatmap view, the frontend will request the corresponding endpoint for the CRIs of all assets or categories for a certain period; if they open a network view, it will query the relationships and SIS of the relevant nodes; if they explore alerts, it will retrieve the list of recent alerts with their details. The API gathers this information (possibly combining data from Timescale, Neo4j, and caches in Redis) and delivers it in JSON or GraphQL format. In this way, the data flow is completed: from the external raw source to a rich visualization in the interface that enables decision-making.

Throughout this flow, the document emphasizes the importance of quality and monitoring. Each ingestion pipeline incorporates validations and discards obviously erroneous data, marking as suspicious those that violate soft rules. Quality metrics are proposed for each source (percentage of valid records, arrival delay, consistency) to be monitored on internal dashboards.<sup>52</sup> This suggests that part of the backend will include data monitoring tools—for example, jobs that calculate these quality KPIs and store them for inspection (perhaps using Grafana/Prometheus). Furthermore, regarding auditing, each alert and calculation carries model version IDs<sup>41</sup> and detailed logs with correlation IDs<sup>48</sup>, indicating that rigorous tracking of each event will be carried out throughout the flow.

Comment: The end-to-end data flow is described quite explicitly in the document, clearly outlining each stage from ingestion to visualization.<sup>53</sup><sup>15</sup> This helps guide the backend implementation in terms of which processes to automate and in what sequence. One point to note is that the document does not specify the specific messaging or ETL technologies for moving data. three stages (for example, it doesn't mention whether ingestion will use a Kafka-type streaming system or
simply scheduled tasks that call APIs and write to the database). However, given that in the

10
architecture figure, “Kafka Topics” appears as an optional input, it's possible that in advanced stages
event queues will be integrated to handle real-time feeds. In the first version, the solution
could implement ingestion with scheduled Python scripts (cron jobs) or small daemons
that perform polling/HTTP fetch, and then directly call normalization functions and the database.

The development team will therefore have to decide on the practical orchestration: for example, using an
internal scheduler (mentioned in the diagram) or a tool like Apache Airflow to
coordinate ETL tasks, depending on the complexity of the data sources.

Performance and Scalability
The proposed architecture is designed under a "resource-constrained engineering" philosophy, optimizing to function with modest resources while allowing scalability if needed. Some key points mentioned:

• Efficient use of limited hardware: In the initial phase, a single machine with a multi-core CPU and perhaps a modest GPU is assumed. Therefore, the backend should leverage parallelism wherever possible (for example, calculating metrics in parallel for different assets using multiple threads or processes) to utilize all cores. If scientific Python libraries are used, it is advisable to ensure they release the GIL or to use distributed processing (multiprocessing, Dask, etc.) for intensive calculations. The GPU could be used for specific tasks such as model training (if there were any deep learning models, which does not appear to be the case at the moment, or to accelerate large matrix calculations).

• Indexes and data partitioning: As mentioned, in TimescaleDB, the
series tables can be partitioned by asset or by group to distribute the load.<sup>56</sup> The document indicates that the
partitioning, index, and computation frequency decisions aim to balance realism versus
computational cost.<sup>56</sup> In practice, this means that the database design and
metric update schedules must be refined: for example, perhaps not recalculating
the metric for each asset on every tick, but grouping calculations into windows, or maintaining indexes
on the time and asset columns to speed up the most common queries.

• API response time: For the user experience, the interface must be
fast, ideally with sub-second responses for typical aggregate queries.<sup>26</sup> This impacts
how the backend is developed: efficient queries will need to be implemented (using Timescale's capabilities for fast aggregations and Neo4j's for optimized pathfinding), and
certain results may need to be precomputed. The consideration of including Redis as a cache is
precisely to meet this requirement in intensive use cases, storing, for example, the
result of the last heavy simulation or the top calculated risks.

• Horizontal scalability: As the workload grows, migration to cloud containers is planned, and
roles may even need to be separated: for example, there could be multiple instances of the risk calculation service running in parallel, balanced to process different segments of the asset universe.

The document explicitly mentions the possibility of using Kubernetes and
load balancers.

This means that the backend should be designed to be stateless,
where possible, to facilitate this duplication. For example, a

FastAPI microservice serving the API should not store non-replicated data in memory, so that multiple instances can handle requests interchangeably.

Timescale and Neo4j databases in this scenario could become bottlenecks, so it is important that they are scalable or clustered (Timescale supports distributed nodes in its enterprise version; Neo4j can scale in a causal cluster). Although this goes
beyond the MVP, it is good practice to structure the code to avoid hindering this (e.g., by avoiding
singleton assumptions or absolute paths).

• Monitoring and logging: To maintain performance and detect bottlenecks, a centralized logging stack (ELK stack or Loki+Grafana) is planned
48 integration. This means that the

11
backend will send structured logs (e.g., in JSON with fields for timestamp, process,
correlation ID, etc.) to an aggregation system. This helps It's useful not only for debugging but also for
monitoring performance (execution times of certain processes, frequency of alerts, etc.).
It's part of the operational quality that will be necessary as the system grows.

Comment: The document provides general performance and scalability guidelines, but
many details are left open to implementation. For example, concurrency limits are not discussed, nor is it addressed whether microservices will use async threads (FastAPI supports async IO, which will be useful for
handling multiple concurrent API queries without blocking). Load testing is also not mentioned,
but it will implicitly need to be planned. In short, the backend should be built in a
modular and efficient manner, ensuring that functionality can be achieved with a single, modest server (thanks to
software optimization), and that subsequent horizontal scaling does not require a complete
re-architecture but rather the deployment of more instances or specialized services.

Practical Implications for Backend Development
Based on the above, the Whitepaper (extended version) provides a high-level technical roadmap for backend development. The most relevant practical implications are:

• Technology Selection and Mastery: The development team should be familiar with Python (especially FastAPI for creating web services and APIs) and with the PostgreSQL/TimescaleDB and Neo4j databases. Setting up the Docker environment with these services is one of the first steps (the roadmap suggests a dedicated Sprint 1 for Docker containers, Neo4j/Timescale deployment, and initial ontology load scripts). It will also be key to be proficient in graph query tools (Cypher query language for Neo4j) and SQL for time series analysis.

• Modular Design from the Start: Although the MVP can run on a single node, it is advisable to develop the components in a decoupled manner. This involves creating independent microservices
for each responsibility (ingestion, computation, alerting, etc.), even if they are initially
orchestrated together. A modular design will facilitate the transition to Kubernetes later.

Practically, this could mean separate repositories or packages for each service, or
at least a clear separation of logic within the code. For example, having a dedicated
service for ingestion that can run separately, instead of a large monolithic script.

• API and data interface definition: Since the whitepaper doesn't go into the details of the
endpoints, development will need to define an API specification (possibly using
Swagger/OpenAPI for REST, and/or a GraphQL schema). Practical implications include deciding on

response formats (JSON with specific structures for assets, alerts, etc.),

paginating or filtering mechanisms for queries (e.g., allowing requests for historical CRIs

within a date range, filtering alerts by severity, etc.), and ensuring that the API meets
security requirements (e.g., all requests must include a valid and reviewed JWT token). It will be
helpful to design this API contractually before implementation to align with the frontend's
needs.

• Authentication and Roles Implementation: While not detailed, a
robust authentication solution will need to be integrated. In practice, using FastAPI, a common approach is to use
OAuth2 with a password (or OAuth2 device flow, etc.) to issue JWT tokens that the frontend uses in
each request. A registration/login system should be planned (for an MVP, perhaps predefined users
if complexity is desired, but in a live product, integration with an OAuth provider

or a small user database with password hashes). Next, middleware to verify JWT on each

12
request and extract the user's role, applying access control on sensitive endpoints. For example,

certain API routes might require the Institutional role (such as downloading complete datasets
via API). Also, in the case of multi-tenants, filter by client ID. All

these considerations must be clearly coded in the backend.

• Integration of real data sources: The document defines data types, but the team

must select and integrate specific providers. In practice, it will be necessary to develop
connectors for APIs such as Yahoo Finance, Bloomberg (if accessible), Alpha Vantage,

central bank APIs for macroeconomics, etc., and possibly scrapers for news or RSS feeds.

These connectors can be separate programs or functions within the ingestion microservice.

Credentials (API keys) must also be handled securely and call limits must be respected.

This is not included in the white paper.paper, but it's an essential task for populating the
system with real data.

• Quantitative calculations and validation: Translating the risk logic into code will require choosing
libraries and testing results. For example, for volatility and other statistics, use pandas/
numpy; for HMM, perhaps hmmlearn; for copulas, specialized libraries. It will be necessary to validate
that the calculations match theoretical expectations (for example, that a high CRI actually
corresponds to historically known risk cases). The white paper emphasizes calibration and
backtesting, so in practice, it would be necessary to create some backtesting scripts or at least
perform manual validation that in historical events (2008, 2020) the system would have given
expected signals. This goes somewhat beyond pure development, but it's an implication for fine-tuning the risk engine.


• Model persistence and versioning: Implementing the logic to version index weights, alert thresholds, etc., may require versioned configuration tables or files. In practice, this could be a PostgreSQL table that stores, for example,

"version 1.2 – CRI weight price=0.3, fundamental=0.2..." with an expiration date. Each time the calculations are run, the system must label which version was used. This adds complexity but is important for auditing. A mechanism will also be needed to update these parameters in a controlled manner (perhaps only an admin can change them, and doing so generates a new version record).

• Logging and monitoring: From the outset, it's advisable to implement microservices with robust logging (using the Python logging library configured for JSON format, for example). Include correlation IDs, perhaps passing a common ID from data ingestion to the generated alert, to enable end-to-end event tracing in the logs. Furthermore, deploying tools

such as Grafana with Prometheus or using an ELK stack will help monitor the application at
runtime. For example, logs of how much data was ingested, how long it took to calculate metrics,

how many alerts were triggered per day, etc., will be valuable for operating the system. Since the
whitepaper mentions it as necessary 48, it is prudent to incorporate it into the architecture from
early on.

• Incremental Roadmap: Functionalities can be built in phases. The document suggests
an implementation order (loading basic ontology, then historical ingestion, then analytical engine,

then UI/alerts, etc.) 57. Following this order makes sense. It implies having the
foundation (DBs, schema, basic data) before attempting complex calculations. For the
development team, this means planning sprints where, for example, the
ontology is initially implemented in Neo4j along with a script to populate it; then a pipeline is created to obtain historical prices and
populate Timescale; Next come the functions for calculating the simple risk vector; later

13

Add SIS and simulation; and finally the front-end and alerts. Each stage builds upon the previous one.

Maintaining this iterative approach will allow for step-by-step testing of the partial system.

In conclusion, the extended whitepaper offers a very comprehensive guide on what the WallStreetWar backend should do and with which main tools. The microservices architecture in Python, the databases to use, and the metrics to calculate are explicitly outlined, which reduces technological uncertainty. Practical details such as the specific API endpoints, the precise authentication mechanisms, the orchestration of internal tasks, and the exact integration of data sources remain to be defined. These gaps will need to be filled with design decisions during development. However, the practical implications are clear: a modular, scalable, and secure backend must be built that processes large volumes of financial data in near real-time, producing explainable and actionable risk indicators. The development team will have to complement the document's strategic vision with concrete technical decisions, but they have a solid blueprint for creating the systemic risk "radar machine" that WallStreetWar promises.
WallStreetWar Backend Technical Specifications
1. Specific Backend Endpoints (REST/GraphQL) by User Role
The system exposes a unified API, accessible via REST and optionally GraphQL, which serves both the web dashboard and external integrations. The main endpoints, with their routes, parameters, and response formats, are defined below. Pagination considerations, filters, and accessibility differences based on user role (Standard/Retail, Pro, Institutional) are also indicated:

• Global Risk Summary: GET /api/risks/summary – Returns an aggregated matrix of current risk levels by group or category. Optional query parameters:

level={group|subgroup|category} to specify the aggregation level,
top_n= to limit to the n groups with the highest risk. The response is JSON with structures like

{"group": "...", "price_risk": X, "liquidity_risk": Y, ...} for each
group. This endpoint is frequently accessed by the dashboard (heat map view) and will be cached
for faster response 2. All roles can access this summary, but the
Standard user will only see simplified metrics (e.g., main categories), while Pro/
Institutional users get full detail by subcategory and exact numerical values ​​3.

• Asset details and risk metrics: GET /api/assets/{id} – Provides detailed
data for a specific asset (identified by its unique ID) including its latest
risk metrics (e.g., its multi-dimensional risk vector) 4, recent history of its
Composite Risk Index (CRI), and metadata (sector, category, etc.). Example response:

{"asset": "XYZ Corp", "group": "...", "current_CRI": 7.5, "risks":

{"price": 0.8,"credit": 0.5,...}, "CRI_history": [...],

"last_update": "2025-12-30T13:00:00Z"} . This endpoint supports query filters

instead of path filters: for example, GET /api/assets?name=XYZ or ?category=RealEstate

to search for assets by name or to list assets of a certain category (in which case the
response is paginated). Standard pagination will be implemented (for example, parameters ?

limit=50&offset=0 or ?page=1&page_size=50), also returning a total
or next/previous page links in the response. Retail users can query asset data but with limited information (e.g., they might see the asset's overall CRI but not all the detailed sub-risks), while Pro and Institutional users see the complete breakdown of all the asset's risk vectors.

• Time series and historical metrics: GET /api/assets/{id}/historical_risk –

Returns the time series of risk scores (e.g., CRI) for an asset or entity over time, for plotting graphs. It supports parameters ?from=YYYY-MM-DD&to=YYYY-MM-DD to limit the date range, and possibly an interval (daily, weekly) if aggregations are allowed.

The response is a chronologically ordered list of points {"date": ..., "CRI": ..., "price_risk": ..., ...}. This endpoint can handle
large volumes of data, so it is recommended to paginate by date or limit the window of

1
time per request. All roles can access the historical visualization via the UI, but
only Pro/Institutional users can export this complete data (for example, a Pro user could
download the historical data in CSV format from the dashboard by internally calling this API).

• Contagion network query: GET /api/contagion_path?origin=A&destination=B – Calculates
and returns the possible contagion path in the risk graph from entity A to entity B.

The response includes the sequence of nodes and causal relationships: for example, {"path":
["Node A", "Node X", "Node Y", "Node B"], "detail": [...details of each
link...]}. This calculation can be costly; it may be restricted to Pro/Institutional users or depth limits may be applied. Institutional users could have this endpoint fully enabled (even via GraphQL for arbitrary graph queries), while a Standard user might not have access to custom contagion analyses but only to those predefined in the interface. If many similar queries are repeated, certain frequent routes could be cached to improve latency. Rate limits will also be implemented in the API for these heavy queries, preventing abuse (e.g., restricting the maximum depth of the queryable graph in public environments).

• Running stress scenarios: POST /api/scenarios – Allows authorized users to run a stress simulation. Stress or what-if scenario. The request body

will include a JSON object with the scenario definition, e.g., { "shock": {"asset": "XYZ Corp", "type": "price", "magnitude": -0.3}, "propagate": true } to simulate
a 30% drop in the price of XYZ and propagate it. The API queues the request internally and

immediately returns a confirmation with a scenario ID (and possibly an initial state) 7. Once the asynchronous calculation is complete, the result is stored (and optionally
notified to the frontend via WebSocket). A client can then use GET /api/scenarios/

{result_id} to obtain the results: for example, a list of affected assets with
their new post-scenario risk levels, aggregated before/after metrics, etc. This
endpoint will only be available to Pro and Institutional users, as Retail users have
predefined stress scenarios in the UI but not the ability to launch arbitrary simulations. Institutional users can define complex scenarios (multiple simultaneous shocks, advanced configurations), while a Pro user might only be allowed one shock at a time. Access control by scope could also be applied (e.g., scope scenarios: execute only, granted to advanced roles).

• Risk event management and alerting: GET /api/alerts – Lists active or
recent alerts generated by the engine (e.g., early signs of high risk). Supports
filters such as ?state=active|attended, ?severity=high|medium, or date range ?from=... to narrow down historical alerts. The response contains fields such as {"id": 123,
"timestamp": "...", "type": "EarlyWarning", "description": "...",
"severity": "HIGH", "related_asset": "...", "threshold": ...,
"value": ...}. It is paginated if there are many historical alerts. Retail will see a limited subset (perhaps only high-level alerts aggregated by risk group), while Pro and Institutional users see all alerts in detail. Additionally, there could be a POST endpoint /api/
alerts/{id}/ack for a user to mark an alert as acknowledged/served – this functionality would make more sense for Pro analysts managing alert queues, or for institutions integrating alerts into their systems (e.g., via an external webhook). Configurable alert rules (e.g., thresholds) could also be exposed to Pro users: for example, PUT /api/config/thresholds (Pro only) to adjust certain alert parameters in their personal view or for their institution. Configuration changes would be protected by role permissions (Institutional users could have global controls, Pro users only local ones).

2

• GraphQL Access (optional): If GraphQL is implemented, there would be a single endpoint (POST /api/graphql) where advanced clients (primarily Institutional users) can query exactly the data they need. For example, a GraphQL query could request, in a single request, the specific fields of several assets and their connections in the graph, optimizing data transfer. This interface would give technical users (e.g., institutional quantitative teams) the flexibility to integrate the engine into their internal tools. Access

GraphQL would be restricted by authentication and roles: it is likely that only Institutional (or regulatory) clients will have credentials with the scope to use GraphQL, given that it allows for greater volume and depth of data.

Differences by user role: The backend applies robust access control to distinguish capabilities according to user type. A Standard User (Advanced Retail) typically does not consume the API directly but through the dashboard; therefore, their permissions are limited to basic read-only endpoints. The information they receive may be already aggregated or reduced in detail.

A Pro User (manager or analyst) has access to more endpoints: they can, for example, export historical data, fine-tune alert parameters, or run certain stress tests through the API. Their responses include greater granularity (e.g., all risk subcomponents of an asset) and they can use advanced filters in their queries. The Institutional/Regulatory User enjoys the broadest level of access: they can use the API programmatically (they may be provided with special API keys or tokens), including the GraphQL interface for custom queries, their own on-premise integrations, as well as endpoints for complex scenarios and detailed reports.

Furthermore, in institutional environments, certain endpoints may offer higher throughput or higher quota rates, given that these are paid accounts and require access to high-volume data. In all cases, the API is secured with role-based authentication and authorizations to ensure that sensitive data is protected. bles
will only be delivered to those who are entitled to them 10. Likewise, appropriate usage limits (rate limiting) will be implemented according to the tier: for example, a Retail client could be limited to X calls per minute even though the application does not normally expose the key to them, while Institutional clients may have higher quotas or even intensive usage agreements 11.

Regarding format, all responses will follow clear JSON structures, with conventional HTTP status codes (200 OK, 400 validation errors, 401 unauthorized, etc.). Descriptive error messages will be included
and, where possible, correlation identifiers in error responses to facilitate
tracing (see logging section). This consistency makes it easier for different clients (web, mobile, or server-to-server integrations) to consume the API uniformly.

2. Recommended Authentication System and its Implementation
in FastAPI
Given the need for robust authentication and strict data separation per user,
it is recommended to use JWT (JSON Web Tokens) under the OAuth2 scheme with password grant to protect
the API. This approach is stateless and fits well with FastAPI, allowing the issuance of signed tokens that the
client will include in each request. Alternatively, for enterprise integrations or federated login,
full OAuth2 could be considered (e.g., support for OAuth2 Authorization Code with an external IdP), but for simplicity, we will assume native authentication with JWT.

Credential Management and Token Issuance: A login endpoint (POST /api/auth/token) will be implemented where the user sends their credentials (username/password or email/password). FastAPI will facilitate this using the OAuth2PasswordRequestForm dependency. The backend will verify the password
against the one stored (previously hashed, using bcrypt or another secure algorithm) in the user database.

If both are valid, a short-lived (e.g., 15-minute) JWT access token is generated.

3
signed with a secret key (or RSA pair for greater security). The JWT will include in its payload the essential user data: their identifier, role (e.g., "role": "pro"), and possibly specific access scopes.

Standard claims such as exp (expiration) and iat (issued on) are also included.

To strengthen security, the JWT token will be sent to the client, who will typically store it in memory or secure storage (in a SPA, in Redux memory, or similar; not in LocalStorage if possible,
to mitigate XSS).

Simultaneously, a longer-lived refresh token (e.g., 7-30 days) is issued, which can be a special JWT or simply a random token stored on the server. The recommended practice is not to send the refresh token to local storage; instead, it could be delivered as an HTTPOnly, Secure cookie with the SameSite flag, so that the frontend can automatically use it in the refresh route. The POST endpoint `/api/auth/refresh` will validate the refresh token (e.g., by checking that it exists in a table of valid tokens and has not been revoked) and, if valid, will generate a new access JWT without requiring re-login. This mechanism allows for persistent sessions without compromising security. Invalidated refresh tokens (e.g., after manual logout or password change) are managed by maintaining a revocation list or deleting them from the database.

Access Roles and Scopes: Leveraging JWT, we will include user role information or even detailed scopes in the token. FastAPI allows us to require specific scopes in security dependencies; for example, to protect an endpoint exclusively for administrators or institutional users, we would use `Security(OAuth2PasswordBearer(...), scopes=["admin"])` or another name, and configure the corresponding validation. In practice, we could define scopes such as `basic`, `pro`, `admin`, etc., or more granular functional scopes (`read:alerts`, `write:scenarios`). A Retail user will receive a token with a limited scope (only basic reads), a Pro user with additional scopes (creating scenarios, exporting data), and an Institutional user with virtually all relevant scopes. When a request arrives, a dependency will check the JWT token: FastAPI will decode and verify the signature and expiration; then we will extract the claims. Based on the role/scope in the claims, a decision is made to allow or reject the operation. This control ensures that even if a Retailer attempts to call an advanced endpoint, the backend will return 403 Forbidden.

FastAPI Integration: We will configure an OAuth2PasswordBearer object to extract the token from the Authorization headers: Bearer <token>. Then, in each protected route, we will add a dependency that validates the JWT and loads the current user (for example, a function that decodes the token and looks up the user in the database or a cache). FastAPI does not store a session; authentication occurs on each request (stateless). Therefore, it is scalable.

We can use libraries like python-jose or PyJWT to handle JWT signing/verification, and passlib for password hashes. For speed, there is FastAPI Users, a package that provides predefined authentication models and routes (including JWT, refresh tokens, and user management) that we could leverage.

User activity logging: It is important to keep track of critical actions performed by each user, both for auditing purposes and to detect misuse. We will implement activity logging: for example, every time a Pro user launches a scenario or modifies an alert threshold, a log will be written with their ID, the action performed, timestamp, and perhaps their IP address. Similarly, login attempts (successful or failed) are logged; this helps detect brute-force attacks or account sharing. These logs could be stored in a user_activity_log table in the database (especially relevant business actions, such as "User X (Pro) adjusted the Liquidity threshold to Y") and/or sent to the central logging system (see Logging section). Even data queries could be logged with less detail (e.g., "User 5 (Retail) queried Energy Group risk at 10:30 AM"). To avoid impacting latency, this logging can be done asynchronously using FastAPI BackgroundTasks or by sending the event to a non-blocking logger.

Additionally, standard security measures should be implemented: blocking policies after several failed login attempts, password storage with a strong salt and algorithm, 2FA capability for sensitive institutional accounts, forced token renewal in case of suspicion, etc. Also, ensure communication over HTTPS so that tokens don't travel in plain text, and
use security headers (CORS appropriate for the legitimate frontend, Content Security Policy, etc.).
With JWTs, since they are self-sufficient, their invalidation must be handled carefully: if a compromised token is detected, we could maintain a list of revoked JWTs (saving their JTI) or
change the signing key on a rotating basis to invalidate them all. This adds complexity, so a
best practice is to limit the token lifetime (e.g., 15 minutes) to mitigate the potential damage of a theft.

In summary, with FastAPI, a robust OAuth2/JWT system can be set up: secure storage of
credentials, token retrieval and refresh endpoints, use of bearer tokens in each call,
role-based route decoration, and activity monitoring. This meets the expected
security and user experience (single token login) requirements of a financial platform.

3. Complete Orchestration of Internal Tasks and Process Execution

WallStreetWar's internal architecture: data flows from external sources into ingestion and normalization pipelines, is stored in TimescaleDB/Neo4j, and then a layer of analytics microservices calculates risk metrics, detects regime changes, and propagates stress scenarios, generating alerts that are exposed to the dashboard via the API.

The platform is designed as a set of specialized Python microservices (FastAPI) for different functions: data ingestion, risk calculation, graph analysis/propagation, alert generation, and the front-end API service. For all these tasks to collaborate reliably, careful orchestration is required, defining when and how each process is executed, how they are chained, and which scheduling technology or task queues are appropriate.

Data Ingestion and Normalization: An ingestion service or module is responsible for connecting
periodically to external sources (see section 4) to obtain new market, fundamental, macroeconomic, and other data. These ingestion tasks can be scheduled using a
scheduler. Several options exist: - Use an asynchronous job queuing system like Celery
(with a broker such as RabbitMQ or Redis) and its timer component (Celery Beat) to schedule

5
recurring tasks. For example, configure Celery tasks to “fetch prices” every 5 minutes, “fetch news” every hour, “fetch macro data” daily at 6:00 PM, etc. Celery allows you to distribute tasks
across separate workers, retry in case of failure, and easily chain operations. - Use
APScheduler (a Python scheduling library) within the ingestion service to launch sub-tasks based on cron expressions. This option is valid for simple deployments, although less robust for scaling. Even a traditional system cron job or Kubernetes cron jobs could launch ingestion scripts at fixed intervals. However, coordinating with the other components would be more manual.

When obtaining new data, the ingestion task also performs normalization.Action: validate formats, convert units, enrich with metadata from the internal ontology, etc. (e.g., map a stock ticker to its internal ID in the database). In compliance with data quality policies, the ingestion process will discard or flag out-of-range or inconsistent data.<sup>15</sup> After normalization, the data is stored in the corresponding databases: time series to TimescaleDB (a PostgreSQL extension optimized for time) and relationships or entities to Neo4j (a graph database).<sup>16</sup> Once persisted, the next step is triggered.

Risk Metric Calculation: The Risk Calculator service is activated after each relevant ingestion. This is where the risk vectors for each asset (e.g., price risk, credit risk, liquidity risk, etc.) and the aggregate indices (CRI – Composite Risk Index, SIS – Systemic Importance Score, etc.) are computed. Orchestration can be chained: for example, using Celery, the ingestion task, upon completion, could invoke (signature or chain) a risk calculation task, passing it information about which assets or groups to update. Alternatively, in an event-driven model, the ingestion service can publish an event (e.g., on a Kafka-like message bus) indicating "new data for assets X, Y"; the calculation service subscribes to these events and, upon receiving them, processes the corresponding risks. In fact, the architecture could combine both approaches: Kafka for streaming very low-latency market events, and Celery for orchestrating higher-level or less frequent tasks (such as recalculating everything at the close of business).

The calculation frequency can vary depending on the type of risk: some vectors are updated in real time (price), others perhaps daily (fundamentals, depending on availability). The engine also calculates aggregate metrics by category/group, propagating risk upwards in the ontology (sum or weighting of component risks). These aggregate calculations can be scheduled at fixed intervals (e.g., recalculating totals every hour) or triggered immediately after updating a critical component.

Regime detection and other periodic analytics: In addition to the base calculation, there are analytical processes such as market regime detection (e.g., using HMM models to identify whether the market is in a calm vs. stressed state) that run over longer time windows. These tasks could be orchestrated as independent jobs scheduled daily. For example, every night at a certain time, run a task (possibly in Airflow if justified) that: 1. Extracts recent risk series, 2. Applies the regime model or calculates systemic correlations, 3. Saves the detected regime (e.g., volatile vs. stable) to the database for display on the dashboard.

Airflow would be a good fit for complex batch pipelines or those with time dependencies, as it allows you to define DAGs (task graphs) with sequential steps, retries, visual monitoring, etc. For example, a nightly DAG could be: Update fundamentals -> Recalculate global CRI -> Run regime detection -> Generate summary report, where each "->" represents a dependency. In large systems, Airflow or Prefect robustly handle these sequences. In smaller systems, Celery can also handle sequentially scheduled tasks (e.g., using countdowns or ETAs for the next task, or simply chaining them within a master task).

6
Stress Propagation and Simulations: When a risk event occurs (e.g., a sudden drop in an asset) or a user launches a scenario, the propagation logic (Graph Analytics Service) comes into play. These potentially intensive tasks are executed asynchronously to avoid blocking the interface. For example, in response to a user-defined shock, the backend (API) queues a simulation job in Celery and returns immediate control. The simulation worker takes the scenario, queries the connection structure in Neo4j, iteratively propagates the impacts (e.g., recalculating risk metrics if a node experiences a loss of X%), and produces a set of results. When it finishes, it stores the results (in a cache or database) and may notify via an event (e.g., using WebSocket or sending a signal to the API layer) that the data is ready for collection. This allows the user to see the simulation's evolution on the dashboard (partial updates could even be sent for animation). Internally, we could implement dedicated Celery queues for scenarios, separate from the ingestion queues, so that a heavy scenario from an institutional user doesn't delay the updating of basic data for other users.

Alert generation: The alerting process can be continuous: after each risk calculation, rules and thresholds are evaluated to see if A certain condition triggers an alert. This can occur within the same calculation task (e.g., at the end of calculating an asset's CRI, checking if it has increased from 7 to 9, exceeding a high alert threshold), or it can be delegated to a separate Alerts service. In a pure microservices architecture, we could have an Alerts service that subscribes to new results (e.g., via Kafka, each new calculated risk is sent, and the service evaluates rules). Alternatively, integrating the logic into the risk service is simpler: after an update, all relevant rules are queried, and alerts are created as appropriate. These alerts are written to the database (e.g., an alerts table with timestamp, type, severity, etc.), and immediate notifications are possibly sent: an email, a push notification, or a webhook for institutional clients who have registered a callback endpoint. The orchestration here is primarily triggered by data events. We could also have a scheduled task that checks for certain slow conditions (e.g., "if the average CRI of group X increased by more than 20% in the last week," this could be checked daily).

Recommended tools for orchestration: In short, Celery is a good choice for handling asynchronous tasks and event-triggered pipelines, given its strong integration with FastAPI (we can send Celery tasks within POST endpoints for long processes, such as scenarios). It allows for retries, queue visibility, and worker scaling based on load. FastAPI BackgroundTasks would be reserved for very lightweight tasks that don't require high availability (e.g., updating a last-visit timestamp after responding to a request). Airflow can complement this for complex scheduled ETL or batch tasks, especially useful if backtesting or ML model training processes that run once a day are incorporated in the future. In the initial stages, a simple scheduler (Celery Beat or cron jobs) plus Celery might suffice; as the logic grows, migrating critical pipelines to Airflow will modularize and make the flow more maintainable.

Inter-service communication: Orchestration also involves how microservices communicate. It's suggested to use a message broker (RabbitMQ, Redis) for both the task queue (Celery) and event-driven notifications. For synchronous requests between services (less desirable due to coupling), internal APIs could be exposed. However, event-driven communication is preferred: for example, Ingest -> [event “new data”] -> RiskCalc listens and processes -> [event “risks updated”]* -> Alerting listens and triggers alerts. This decoupled design improves scalability and resilience: each service can retry or process at its own pace, and if one fails, messages accumulate until it recovers, preventing losses.

Finally, it is important to monitor and manage these tasks (see section 7 of logs/metrics).
We will configure queue health metrics: Celery queue size, average execution times,

7
etc., to detect bottlenecks. We will also use correlation identifiers in task chains to be able to track a complete process (from data ingestion X to generated alert Y).
The orchestration designed in this way ensures that the different backend modules work in harmony, processing data from input to generating insights in the form of alerts and visualizations, in a timely and reliable manner.

4. External Data Sources and Their Integration (Prices, Fundamentals, Macroeconomics, Events, Sentiment)
The solution requires a variety of financial data. The following are suggested specific providers (public or freemium APIs) for each type of data needed, along with considerations for authentication, rate limits, formats, and scheduled updates:

• Market prices (stocks, indices, commodities, crypto): For stock and ETF prices, a popular option is the Alpha Vantage API, which offers intraday and daily quote data in JSON/CSV format. Alpha Vantage has a free tier with a limit of approximately 5 calls per minute and 25–500 calls per day, sufficient for prototypes but potentially limited for production (e.g., quotes for many symbols). Another freemium API is Finnhub, which provides real-time data for stocks, Forex, and crypto; its free plan allows approximately 60 calls per minute with certain monthly caps, and it also offers WebSockets for real-time pricing. IEX Cloud is another alternative for US stocks with a free tier (registration required). For cryptocurrencies, open sources like CoinGecko or Binance API allow you to obtain spot prices at no cost (CoinGecko even without an API key, with decent rate limits). In all cases, integration is done via HTTP GET requests, authenticating with an API key

(passed as a parameter or header). The ingestion backend will manage these keys securely
(environment variables, Vault, etc.) and respect the rates: for example, if Alpha Vantage
allows 5 per minute, the ingestion task will implement delays between calls or combine
symbols into a single call if the API supports it. Since prices are critical and frequent,
it's advisable to temporarily cache results to avoid repeatedly hitting the external API; for example,
storing the latest quotes in Redis for a few seconds. Scheduled price updates
could be: intraday every 5-15 minutes (or streaming if high
frequency is required) and daily market close to consolidate OHLC data. It's also possible to use
sources like Yahoo Finance via Python libraries (yfinance) for certain historical data, although
these are not official APIs and carry a risk of blocking; it's better to rely on providers with SLAs.

• Fundamental data (financial statements, ratios, etc.): Fundamental data is typically
available less frequently (quarterly, annually). A useful API is Financial Modeling

Prep (FMP), which in its free tier offers some endpoints for financial statements,
company metrics, and ratings. For example, FMP allows you to obtain a company's balance sheet, income statement,
and cash flow in JSON, with reasonable daily limits. Alpha Vantage
also provides fundamental data (e.g., company overview, earnings per quarter)
within its endpoints, although the 500/day limit can be a bottleneck. For a broader
set, Finnhub includes global fundamental data (ratios, ESG, etc.), but much of it
requires a paid plan. As a public resource, US company financial reports
are in the SEC's EDGAR database (API available, but it returns XBRL/XML data that needs to be
parsed). For our purposes, using preprocessed APIs like FMP/Alpha is more straightforward. The
integration of fundamentals would perhaps be done once a day or once a week: for example, a
process that checks each night which companies have reported recent results

(possibly combined with an earnings event feed) and calls the API to
update that data in our database. Since fundamentals change little, they will not saturate the

8
limits if well planned (e.g., dividing the calls for 1000 companies by day, etc.). Format:

JSON with financial fields that will need to be mapped to our ontology (e.g., total debt, assets, EBITDA, etc., which could feed a fundamental risk indicator). This
data will be stored in TimescaleDB with a timestamp for historical queries (e.g.,
ratio evolution) or directly as the latest figures to calculate solvency risks.

Important: control the quality, as different APIs may use different units (thousands,
millions) or have update lag.

• Macroeconomic data: Here we have excellent public sources. The main one is the
FRED (Federal Reserve Economic Data) database, with an open and free API that provides
thousands of macroeconomic series (interest rates, GDP, inflation, unemployment, etc.). FRED requires an API key
(free) but has very broad limits (practically not a problem for normal
use). Other sources include: the World Bank (World Bank API) for global development indicators, the OECD API for data from developed countries, and APIs from specific central banks

(for example, the ECB has APIs for some Eurozone series). For Treasury bond prices or yield curves, the U.S. Treasury Department itself offers daily data in
XML/CSV format. Macroeconomic data ingestion can be scheduled according to the frequency of each indicator:
many macroeconomic data points are updated monthly or quarterly (e.g., CPI, GDP), so a single
monthly scheduled task is sufficient. However, some, such as interest rates, can be updated daily.

Calls could be grouped: for example, a weekly job that updates all the relevant macro series.
Formats are usually JSON or CSV; they will need to be parsed and normalized (converting
percentages to decimals, etc.). These series will go to TimescaleDB to be combined with other
temporal data. Time zones and release dates must be taken into account: it's advisable that our
ingestion system knows the publication schedule (e.g., if the employment data is released on the first Friday
of the month at 8:30 ET, schedule the ingestion for that time to capture it immediately). If
we need real-time notifications of macro events (e.g., knowing the minute-by-minute when the
Fed raises rates), we could subscribe to financial news services, but that falls under
events (next (point). Authentication: Most of these APIs (FRED, World Bank) simply require the key in the URL. Rate limits are usually generous (FRED requires a maximum of 120 calls per minute, for example). With caching, we could even store locally the series that hardly change (e.g., annual GDP) and update only when new values ​​are announced.

• Financial events (corporate and economic) and news: For corporate events (earnings, splits, mergers, etc.), some free APIs provide limited data. Yahoo Finance has unofficial endpoints for earnings and split calendars that can be leveraged with light scraping via yfinance. Financial Modeling Prep offers a feed of upcoming earnings and IPOs in its API. Another alternative is EOD Historical Data (freemium), which has a calendar of global corporate events. This data would be updated daily, filtered by companies in our universe. Regarding macroeconomic events (economic indicators, central bank meetings, etc.), a public economic calendar could be used. APIs like TradingEconomics (freemium) provide a calendar of upcoming economic releases with dates and consensus estimates. Alternatively, Investing.com has a feed (although its API is not open source, web scraping would be necessary, taking care to review the terms of service). Since our systemic risk system might want to anticipate events (e.g., "US inflation is announced on such and such a day, which could impact risk"), integrating an economic calendar allows us to generate proactive alerts. For news and sentiment (see the next point for sentiment analysis), the NewsAPI is useful for real-time financial news headlines; its free tier allows approximately 100 requests per day, returning headlines and summaries in JSON. We can use it to track unexpected market events (company bankruptcy, political crisis) in near real-time. The plan would be to have a task that queries the NewsAPI every 10-15 minutes with relevant keywords (group names or key assets) and processes the news.

9

Format: JSON with fields title, description, source, publishedAt, etc.

We will perform text analysis to classify the news in our ontology (which group/asset
does it affect?) and store important events in our database/event store. Also, for critical events, we could configure webhooks or subscriptions: for example, if available, use a webhook from a news provider that I set up to our system when something big happens (some premium services offer this).

• Market sentiment (social media, quantified news): Sentiment is a less structured data point, but there are approximations. One way is to analyze the news sources
mentioned: using the NewsAPI itself or another provider, apply NLP (Natural Language Processing) algorithms

to score the tone of the headlines/articles (for example,

using a pre-trained model or libraries like NLTK/VADER for sentiment scoring).

Some APIs already provide sentiment: Finnhub, for example, has a News Sentiment endpoint that

analyzes aggregated news about a company (requires at least the basic plan). Another source

is the StockTwits API, which allows you to extract public messages about tickers, from which
we could infer retail sentiment (StockTwits is free with a decent rate limit). The Twitter
API used to be a primary source for sentiment, but its new policies severely limit
free access (now perhaps only 1,500 tweets/month in the free tier). Even so, we could subscribe

to some key accounts (e.g., the Fed, CEOs) for very important events. Reddit (e.g., r/wallstreetbets) is another source of retail sentiment: its public API allows some reading of new posts; combining this with NLP can detect hype or concern about certain assets. Integrating sentiment will involve scheduling frequent tasks (every X minutes) that collect and analyze recent messages. Given the potentially large volume, this might be limited to more critical assets (e.g., the top 50 by systemic importance). The results (a sentiment index per asset or sector) are saved and incorporated into the qualitative risk vectors. Regarding limits: the StockTwits API limits ~400 requests/hour without a token, Twitter's free access is currently very low, and the Reddit API limits ~60 requests/minute. Authentication varies: StockTwits does not require authentication for basic reads, Twitter requires OAuth2 (Bearer Token), and Reddit uses OAuth2 client credentials. We will implement adapters for each source with exponential backoff in case of code 429 (rate limit exceeded) and with caching of results (e.g., n or analyze the same news item/tweet twice. We will likely consolidate this into a sentiment ingestion process that gathers data from multiple sources and produces a unified metric.

General Integration: All these providers require managing API keys and adhering to terms of service. We will create a section in the backend configuration for external API credentials, separating environments (sandbox/production). To manage rate limits, we will apply several strategies: (a) distribute calls over time (for example, if we have 500/day in Alpha Vantage, don't request them all at once; use internal caching to avoid repeating the same queries on the same day), (b) implement priority queues for external calls, ensuring that, for example, live pricing calls are not blocked by a flurry of less urgent fundamental calls, (c) monitor the number of calls being made with metrics and pause appropriately upon receiving 429 responses. In case we approach limits, we have a fallback: for example, if
Alpha Vantage runs out, we could temporarily switch to Yahoo Finance scraping as a
contingency (not ideal, but it guarantees continuity).

The data format of each API will be transformed to our unified model. This involves creating
specific mappers/parsers: one for prices (converting Alpha Vantage JSON to our price tables), another for fundamentals (mapping FMP fields to our standard fields), etc.
We will maintain documentation of these mappings for traceability. In addition, we will record the source and
timestamp of each ingested data point (metadata in the database) for future quality audits (see the
versioning and auditing section).

10
Finally, we will plan appropriate scheduled updates for each flow: near real-time prices, quarterly fundamentals, monthly macro, and daily/intraday sentiment. This is coordinated with task orchestration: each type of ingestion will be a recurring task configured according to its
optimal frequency. In this way, the engine will always have up-to-date data feeding the systemic risk calculations.

13 23 summarize this external integration strategy: connectors to market data providers, macroeconomic APIs, and messaging systems (notifications) are planned, integrated into the backend. Should the data volume grow or greater reliability be required, switching to robust paid providers (e.g., a Bloomberg/Refinitiv subscription for institutional use, if the project scales) will be evaluated, but initially the aforementioned sources cover the needs in a cost-effective manner.

5. Cached Endpoints/Events and Low-Latency Caching Policy
To guarantee low latency in frequent queries without compromising consistency, we will implement a caching layer (e.g., in-memory Redis) to store responses from certain endpoints and recent calculation results. Not all data will be cached – only data that is costly to generate or frequently requested, and whose freshness can be temporarily relaxed without impact.

We identified the following prime candidates for caching:

• Aggregate risk summaries: Endpoints such as /api/risks/summary or /api/top_risks (top N riskiest assets) will be aggressively cached. Since they summarize the global state, they are typically recalculated with each update cycle (e.g., every 5 minutes). Instead of recalculating them on every request, a background job will recalculate them periodically (e.g., once per minute) and store the JSON result in Redis 2. User GET requests will simply read from the cache, achieving sub-second response times even under load. The expiration policy could be ~30-60 seconds for this data, or

active invalidation: that is, every time the engine finishes updating the risks, it pushes the
new values ​​into the cache (immediately invalidating the old ones). This avoids prolonged
inconsistencies – the maximum inconsistency would be the window between two calculations (e.g., 1 minute). For

Retail/Pro, this freshness is more than sufficient; Institutional clients might require data on a second,

in which case the interval could be lowered or subscriptions to real-time updates could be enabled

via WebSocket instead of caching.

• Details of assets and recent metrics: The first query to /api/assets/{id} for a
given asset can perform several reads (Timescale for series, Neo4j for neighborhood, etc.).

We can cache a snapshot of the combined data for the asset. For example, cache the
current risk vector and latest calculated metrics for each asset (perhaps hundreds or thousands of
keys in Redis, one per asset). Since risks are recalculated periodically, the cache entry for an asset is updated at that time. Thus, repeated queries to the same asset (very common if multiple users inspect the "problem asset of the day") are served quickly from memory. The TTL of these entries could be equal to the risk recalculation period (e.g., 5 min) or managed by active invalidation (updating the cache when there is a new value).

Similarly, we can cache parts of an asset's risk history: for example, the last 30 days of CRI already queried can be cached for sliding charts, updating it daily with the new data and truncating the oldest.

11

• Static ontology and metadata structure: Data such as the complete list of Groups,
Subgroups, and defined Categories (the risk ontology) change very rarely. These can be cached indefinitely in memory (local process cache or Redis) and only invalidated manually if there are changes to the taxonomy. Endpoints like /api/ontology or /api/categories that return these structures don't need to query the database every time.

This improves latency on initial dashboard loads, for example.

• Costly graph analysis results: If an endpoint like /api/contagion_path or a stress scenario produces a complex result, it's worth caching it (at least temporarily), especially if multiple users might query similar paths. For example, once the contagion path from A to B is calculated, save it with the key path:A->B for a few hours. The probability of the same query might not be very high, but if it happens (or if a user repeats the operation), we'll save seconds of recomputation. The same applies to

scenario simulations: the results of a scenario ID can be cached so that the
dashboard loads them without repeatedly querying the database. Since scenarios are usually
on-demand, the cache here serves more for temporary storage and for sharing
results among users (e.g., if an analyst marks a scenario as public for their team,
others can access it via ID without recalculating).

• Current alert list: The list of active alerts (GET /api/alerts?status=active)
is also a good candidate for short-term caching. For example, we could update it
in the cache each time an alert is generated or resolved (invalidating or rebuilding the list) or
simply with a TTL of 10-15 seconds. This is because the dashboard might refresh the list
frequently to notify the user, and it's preferable not to query the alert database
on every poll. Since the number of active alerts at any given time
is likely small (and their importance high), inconsistency should be minimized – it's best
to update the cache on-event. We will implement a system where, when the alert service inserts a new
alert, it also updates the cached entry of active alerts (or invalidates it to be rebuilt on
the next read). This way, we maintain low latency and strong consistency for this case.

To implement this cache layer, we will use Redis, already provided in architecture 24. FastAPI does not include
a built-in cache, but we can integrate a Redis client (e.g., aioredis or redis-py) and create a
decorator or utility that first attempts to obtain the response from Redis and, if it doesn't exist (cache miss),
executes the original logic and then saves the result. We will also consider caching at the
infrastructure level: enabling caching at the delivery layer (e.g., a CDN or a proxy cache in front of the
API). If some GET endpoints are completely public or the same for all users, they could be cached at the CDN level (for example, using Cloudflare to store the response for a few seconds). However, with authentication, the CDN typically doesn't cache (unless we use token-based caching, which complicates things). A more feasible option is an internal reverse proxy (Varnish) that caches certain routes regardless of the user, if it's safe to do so. For simplicity, we'll initially focus on Redis in the backend.

Optimal caching policy (consistency vs. performance): We'll adopt a combination of proactive invalidation and Time-To-Live depending on the data type: - For data whose change is deterministic or event-driven (e.g., risk summaries after recalculation, alerts after events): we'll use immediate invalidation or updates. That is, the process that produces the new data will be responsible for refreshing the corresponding cache. This ensures that the client never receives outdated data with a delay of more than a few milliseconds.of propagation. For example, when recalculating the risk
of Group 1, the risk task will update the “Group 1 risk” entry and the overall aggregation in Redis.
- For data that changes continuously or very frequently (e.g., live market prices if we were caching them), a short TTL ensures freshness. For example, if we were caching quotes,

12
we could set a TTL of 5-10 seconds, so that after that time the source (or the updated database) is forced to be queried.
- For ad-hoc queries (e.g., contagion path) where we cannot predict invalidation, we will use a moderate TTL (e.g., caching for 1 hour). This frees up resources if no one repeats the query soon, and avoids retaining potentially irrelevant results. - Eviction policies: In Redis, we will configure maximum cache sizes and LRU (least recently used) policies so that, in the event of a heavy cache load, older, inaccessible entries are automatically discarded, while the most popular ones are retained.

One challenge is role-based caching: since different users may see different responses from the same endpoint (for example, /api/assets/{id} delivers fewer fields to Retail than to Institutional), we must avoid serving cached data with sensitive information to a Retail user. We will manage this by incorporating the user role or identifier into the cache key when the response differs. For example, the key could be risk_summary:role=pro vs. risk_summary:role=retail if the views are different. Alternatively, we could cache the entire version and filter fields in the application layer based on user role before sending (in fact, this is a good approach: cache all the data and filter/skip fields not allowed for that user in each request). This method reduces cache duplication and ensures derived consistency (the underlying data is the same, only the retail server sees a subset).

Finally, it's important to monitor cache effectiveness: metrics such as hit rate vs. miss rate, response times with and without caching, etc., to adjust TTLs. We'll also be careful with concurrent invalidations: in a distributed environment, two service instances could try to refresh the same cache; mechanisms like Redlock can be used if necessary, although with infrequent updates, this is probably not a serious problem.

In short, intelligent caching will allow us to achieve the instant responses that the dashboard and integrations require, offloading a lot of work from databases and repetitive calculations, but without introducing noticeable inconsistencies thanks to the controlled expiration and refresh-on-update strategy.

6. Versioning and Auditing of Models and Calculation Parameters
A fundamental requirement in a risk system is the ability to version each model and set of parameters used, to know exactly what configuration was used for calculations in the past and to guarantee reproducibility and auditability. To this end, we will implement a robust versioning scheme at both the analytical model level (e.g., the CRI algorithm and weights, the SIS, regime prediction models) and the business rule parameters level (e.g., alert thresholds).

Storing Model and Parameter Versions: Each model or logical block of the quantitative logic will have a unique version identifier. For example, we will define entities such as: -
CRI Model (Composite Risk Index): versions 1.0, 1.1, etc., each with a defined set of weights for each risk vector, an aggregation formula, and possibly normalization methods. - SIS Model (Systemic Importance Score): a separate version, if applicable, with its methodology. - Regime Model (HMM or other): also versioned in case of recalibrations. - Alert rules and thresholds: these logical parameters (e.g., "red alert threshold for CRI > 8") can be versioned by grouping them into an identified set (e.g., "AlertRules v1").

To manage this, we will create either versioned metadata tables in the database or versioned configuration files (or both). A clear strategy is to have a table, for example,
model_config, with columns: model_name (text, e.g., "CRI"), version (text or number),

13
parameters (JSON or specific fields), creation_date, description, created_by. Each time a model is adjusted, a new row is inserted with an incremented version. You can use semantic versioning (major.minor.patch) or simply incremental code. The important thing is that previous configurations are not overwritten but are recorded. Additionally, there can be specific tables: for example, a cri_weights table that stores the weight vectors for each version, or a YAML file for each version stored in version control. nes (Git). Since the
production query needs to be fast, we will likely load the active version into memory when
starting the risk service (or cache it), but save all versions in the database for historical records.

Version correlation with calculations and alerts: Each risk calculation or alert generation process will have an associated model version identifier. That is, when the engine calculates the CRI
of all assets today, it will internally know which CRI version it is using (e.g., v1.2) and record that
data. For example, let's assume a risk_calculation_log table for auditing executions, with
columns: date, calculation_type (e.g., "Daily Risk Update"), used_cri_version, used_sis_version, used_regime_version, etc., and perhaps a summary of results (number
of assets updated, etc.). Similarly, the alerts table could have columns for
rules_version and/or models_version to indicate which configuration triggered that alert.

This means that even if we change the thresholds in the future, we can see that a historical alert
was generated under the previous version of rules.

With this scheme, reconstructing the exact context of any result is possible: simply look at
the version flag in the log and then consult the definition of that version in the model tables.

This is invaluable for audits—for example, if a client asks, "Why didn't the system alert
about risk X last month?", we can verify which rules and weights were in effect at that time and
reproduce the calculation with those same versions to explain it.

The recommended practice is that every change to a model or parameter be documented and reviewed. We will implement a procedure: when a developer/data scientist wants to update, say, the CRI weights after new backtests, they must: 1. Create a new version (e.g., 1.3) in the corresponding table with the new weights. 2. Fill in the metadata fields: reason for change (e.g., "Recalibration after 2025 volatility, improved prediction in the tech sector"), expected impact (e.g., "CRI will increase by ~5% on average in the tech sector, decrease in utilities"), and perhaps a link to backtesting or validation results. 3. Ideally, a reviewer or committee would approve this change (this process can be off-system, but we could record an approved field). Then, implement the change in the code if required (if it's only weights, there's no code change; if it's an algorithm change, there will be a referenceable code commit). 4. Deploy the new active version in production (update any "current version" flags in the database or configuration). From then on, all new executions will use v1.3 and will be logged accordingly.

The platform could include a central versioned configuration system in the form of a file (for example, a JSON/YAML file containing all constants and weights, with a global version field). This file could reside in a Git repository, so that each commit corresponds to a configuration change. However, managing it in the database offers more flexible queries.

A hybrid solution is to maintain the source of truth in the database (for easy access from services) and dump these tables to versioned files to store in Git as a backup or to facilitate change reviews (configuration pull requests).

Another element to version is the trained machine learning models, if any (for example, if an HMM is trained for regime detection, or if there is a neural network model for risk prediction). In such a case, each trained model is stored (e.g., as a pickle file or in

14
ONNX) with a version ID and is maintained in a model repository (this could be in the file system, in S3, or in a blob table). Tools like MLflow or DVC can be useful for tracking models with datasets, but this might be overkill for our scenario. Identifying the version and saving the file in storage with that name is sufficient.

26 highlights this strategy: “All relevant models and weights (CRI, SIS, HMMs, alerting rules) are saved with a version identifier and metadata,” and each execution/alert saves that ID, ensuring historical reconstruction. Likewise, any change requires recording the reason, expected impact, and backtesting results, which aligns with our proposed descriptive fields and approval process.

Future traceability and auditing: With the existing infrastructure, we can answer audit questions such as, "What was the exact engine configuration on day X?" – a snapshot of all active versions could be saved periodically (although if all executions are logged, this can be deduced). Comparing versions will also be easier: for example, we could develop a small internal tool. to list differences between versions (since the parameters are in JSON, a textual diff can even be automated). For regulatory audits, having this ability to reproduce results is crucial for confidence in the engine.

Finally, we relate this to code control: in addition to parameter versioning, software (code) versioning must be synchronized. That is, if the CRI formula (not just weights) is changed in system version 2.0, there would be a corresponding v2.0 code tag. In our audit, we would note that from a certain date onward, v2.0 code with the v2.0 CRI model was used, etc. A comprehensive approach is to maintain triple versioning semantics: v<major>.<minor>.<patch>, where major implies fundamental logic changes (not comparable to the previous version), minor represents recalibrations or compatible improvements, and patch represents minor adjustments. But for the level of detail required, it suffices to

ensure that no previous configurations are lost and to link calculations to versions.

With this approach, the system maintains a high level of model governance, allowing for
continuous improvements without sacrificing historical transparency.

7. Log Structure and Operational Metrics for Monitoring
To operate and maintain a critical backend like this, it is essential to have detailed logs and
operational metrics that allow monitoring the health of each component. We propose an
observability strategy based on proven open-source tools: an ELK-type stack

(Elasticsearch + Logstash + Kibana) or alternatively Loki + Grafana for logs, complemented
with Prometheus for quantitative metrics, and traceability through correlated identifiers.

Structured and centralized logging: All microservices (ingestion, calculation, alerts, API) will log events in a structured format (JSON), including key fields such as timestamp, level (INFO, WARNING, ERROR), service name, and correlation ID. The latter is a UUID generated, for example, at the beginning of a cycle (data batch ingestion or scenario API request) that propagates throughout subsequent calls/tasks. Thus, if a market data ingestion with ID 1234-5678 triggers a risk calculation and then an alert, all logs involved will contain correlation_id=1234-5678. This greatly simplifies reconstructing the sequence of events in an incident. FastAPI allows the use of middleware to assign request IDs to each incoming request (using the X-Request-ID header if present, or generating a new one). For
asynchronous Celery jobs, we can pass the ID in the context or message.

15
Logs will be centralized using an ELK or Loki-type system. In a containerized deployment, it's common to send stdout/stderr from each container to an aggregator. For example, you can deploy Filebeat/Logstash to capture application logs and insert them into Elasticsearch, and then view them in Kibana with powerful filters and search capabilities. Alternatively, Grafana Loki is a newer solution: a log storage engine indexed by tags; the Promtail agents in each service send the logs to Loki. Grafana then allows you to query these logs (similar to how it would be done in Kibana) and also create alerts based on patterns (via Grafana/Loki alerting). Both options are viable; the choice may depend on resources (ELK is more RAM/CPU intensive than Loki). In any case, the log structure will also include user information when applicable (e.g., the user ID that made the request in API logs, to track user actions along with technical activity).

In the logs, we will capture not only errors but also important informational events. For example:
- Upon completion of an ingestion task, log "Ingestion completed: source=AlphaVantage, 120 new records, time=4.2s".
- Upon triggering an alert, log "ALERT triggered: id=ALRT_987, type=EarlyWarning, active=XYZ, level=HIGH, rule_version=2.1".
- Any exceptions or tracebacks will be recorded as ERRORs along with the context (ideally using a structured logger that includes a separate stack trace field). We could even include debug logs in the staging environment to fine-tune algorithms, although in production they will be kept in INFO/WARN/ERROR to avoid overloading the system.

These logs will be retained for a period (e.g., 90 days online, then archived) to meet audit requirements, especially those related to risk decisions. Institutional clients highly value this traceability, so we could disclose, upon request, certain extracts of auditable logs (for example, a monthly report of all generated alerts with their timestamps and reasons).

Operational metrics (monitoring): Complementing the textual logs, we will collect real-time numerical metrics on system behavior, using Prometheus as if Collection system. Each microservice will expose an endpoint /metrics (in Prometheus format) where it reports various metrics: - Performance metrics: endpoint response time (we can use FastAPI middleware or WSGI instrumentation to measure request durations), request count by type, number of Celery tasks executed, average duration of risk tasks, etc. - Resource metrics: CPU usage, memory, open database connections, etc. If we are on Kubernetes, we can obtain this automatically via cAdvisor/Prometheus. At the app level, we can instrument the size of the task queue, the length of Kafka queues, etc. It is suggested to expose throughput metrics and queue lengths per microservice for this purpose. - Domain metrics: for example, number of alerts generated in the last hour, severity distribution, asset with the most alerts, etc. These business metrics can be derived and displayed periodically, helping to identify trends (e.g., a spike in alerts may indicate increasing volatility). - Health status: error counters
by type (e.g., how many times ingestion failed due to an external API timeout), the last time each pipeline
executed successfully, etc.

Prometheus will collect these metrics at intervals (say, every 15 or 30 seconds), and we can create
dashboards in Grafana to visualize them. For example, a dashboard showing: latency of key endpoints (p95), API 5xx error rate, data ingestion rate (records/minute), execution time of risk calculations, memory used by Neo4j, etc. Also, business graphs showing the evolution of the number
of active critical alerts per day, etc., which could be correlated with external events.

Additionally, we will configure operational alerts: Prometheus Alertmanager or Grafana can monitor metric thresholds. For example, if the summary endpoint latency rises above 2 seconds on average, or if the number of queued tasks exceeds a certain value (indicating that a service may be down or slow), or if no risk update has been received for more than X minutes (possible ingestion failure), then we will send notifications (email/Slack) to the technical team. This ensures a rapid response to problems before users notice them.

Logging structure in the cloud context: If we deploy in the cloud, we could integrate with native logging/monitoring services (e.g., CloudWatch on AWS, Stackdriver on GCP), but using ELK/Prometheus Grafana provides portability. We will implement log aggregation either by deploying the stack in the cluster or using a managed Elasticsearch service. It's important to ensure that logs from different environments (dev/staging/prod) are separated or tagged to avoid mixing them.

To correlate logs and metrics, we can include the correlation_id as a tag in certain metrics as well (e.g., measuring the duration of an end-to-end task chain), although correlation is usually analyzed via logs/traces rather than metrics. We can also use distributed tracing systems (such as Jaeger or OpenTelemetry) to capture timings for each service per request; however, this is more complex and perhaps unnecessary initially given that we have quite a few discrete events.

Finally, significant business events (e.g., "Systemic alert issued for Group 1") could be sent not only to logs but also to an internal notification channel (e.g., a Slack webhook for the team) for immediate visibility. This complements technical monitoring with an awareness of what the engine is indicating in terms of risk.

In summary, we will combine structured logging with traceability and a comprehensive metrics system.

This allows us to quickly investigate any incident (e.g., if a user reports unusual data, we search Kibana for the correlation_id of their request and see the entire trail), optimize performance by detecting bottlenecks (Grafana showing if the risk calculation is taking longer than expected), and demonstrate reliability to clients (we can provide reports on availability, average response times, etc., based on these metrics). This observability layer, with well-configured tools such as ELK, Prometheus, Grafana, and Loki, is essential for operating a risk engine in production and meeting the transparency requirements of institutional users and regulators.
Technical and Visual Proposal for the WallStreetWar Frontend (Advanced Retail Profile)
Frontend Technical Architecture
The WallStreetWar frontend will be implemented with React using Next.js (React with SSR/SSG capabilities) as the preferred framework. Next.js offers robust routing and server-side rendering, useful for future SEO needs or optimized initial load times, although in this application, most views will be under authentication (internal dashboard) and will primarily function as a client-side SPA. Communication with the backend will be via REST API to obtain financial data, risk metrics, alerts, etc. All requests to the backend will include robust authentication using JWT to ensure security, meeting the requirement of a secure interface (strong authentication and data isolation per user). TypeScript will be used to improve reliability during development and facilitate scalability. The application will be designed with performance in mind (fast queries, <1s for typical aggregations) and the explainability of each visualization (each chart or alert must be justifiable with supporting data as per the whitepaper). The overall architecture will include, from the outset, JWT integration, state management for remote and local data, and a modular design that facilitates the future incorporation of other user profiles (professional, regulatory) without rebuilding the foundation.
Initially, it will run in a local environment (pure development with npm run dev or a Docker container), but will be ready for easy scalability and deployment to production.

Folder Structure and Modular Organization
A modular structure based on functionality will be adopted, following best practices for feature-driven architecture in Next.js. Instead of strictly grouping by file type (components, services, etc.), we will organize the code by feature modules to maximize cohesion. For example, we could have modules such as auth (authentication), dashboard (main screen), alerts (alert system), stressTest (stress simulator), etc., each with its own internal subfolders. A possible structure would be:

plaintext
src/
├── app/ # Next.js routes and layouts (App Router)
├── components/ # UI components actually shared between modules
├── features/ # Functional modules by feature
│ ├── auth/ # Auth module (login)
│ │ ├── components/
│ │ ├── hooks/
│ │ ├── services/
│ │ └── types/
│ ├── dashboard/ # Main dashboard module
│ │ ├── components/
│ │ ├── hooks/
│ │ ├── services/
│ │ └── types/

1
│ ├── alerts/ # Alert management module
│ └── ... # Other modules (visualizations, etc.)
├── lib/ # Core utilities (e.g., API client, common functions)
├── styles/ # Global styles (e.g., themes, global CSS)
└── types/ # Global TypeScript types 2

In Next.js, the app/ (App Router) folder allows you to define common layouts and pages by route.
We will use a root layout that wraps the application (including the side or top navigation bar, theme provider (light/dark), and authentication context). Within app/, we will define pages such as /login (public) and private pages such as /dashboard (accessible only after login). The features/ folder will house code specific to each feature, keeping together components, hooks, and services related to that feature, which improves cohesion and makes it easier to maintain or assign parts of the code to different teams. Truly reusable shared components across modules (for example, a generic chart component, custom button, modal, etc.) will reside in components/.

This modular organization facilitates scalability: each new feature (e.g., new views for professional users) can be added as a separate module without hindering existing ones.

Furthermore, we follow the recommendation to "organize code by what it does, not what it is," avoiding scattering related files across different technical folders. With clear boundaries between modules, we avoid implicit dependencies. If one module needs logic from another, this logic will be exposed in a controlled manner via exports, keeping the code maintainable and easy to refactor.

Suggested Key Interface Components
For the advanced retail profile, we propose a series of key components and views focused on providing actionable information in a simplified way (remember that the Standard User (advanced retail) will see simpler views with fewer configuration options than a Level 5 Professional). The suggested components, aligned with the functionalities described in the whitepaper, are:

• Hierarchical Map / System Radar: A A navigable view of the global financial system, which
allows exploration of the asset ontology in a drill-down manner (from risk groups to subgroups,
categories, and finally individual instruments). This functions as an asset “radar,”

showing where systemic risk hotspots are concentrated. One possible representation
is an interactive tree or sunburst where the user can expand groups and see
aggregated risk metrics by segment. According to the whitepaper, the first functionality of the
MVP is a “navigable hierarchical map of the financial system, from risk groups to
specific instruments,” which justifies this component. For advanced retail users, this view
would be relatively simplified: it would show the main sections and allow zooming in on
a specific group to then list or visualize its assets.

• Risk Heatmap: An interactive heat map that presents, at a glance, which market segments
are showing anomalously high risk. For example, rows/columns
could be groups and subgroups, colored according to a composite risk index (CRI) or other
metric. The main dashboard will include a global risk heatmap to identify hotspots of
fragility. This component allows the retail user to visually detect which areas (e.g.,
“leveraged loans” or “real estate”) are at high risk levels (warm colors) in recent
weeks. The heatmap will be supported by multidimensional risk vector data
calculated for each asset and aggregated by category. The

2
implementation could use a charting library (e.g., D3.js, Highcharts, or Recharts)
that supports heatmaps, with hover tooltips to provide detailed values.

• Signals and Alerts Panel (Buy/Sell): A side panel or section of the dashboard listing the
alerts generated by the systemic risk engine. The system provides alerts with different
severity levels and explanations. For advanced retail users, these alerts can be
interpreted as signals for potential action (for example, if a certain asset or sector on the network
shows increasing stress, it could be a signal to sell related positions, or if an
undervalued asset is detected, perhaps a buy). The panel will display each alert with a color code (e.g.,
yellow, orange, red according to severity) and a brief description, and selecting an alert could
highlight the assets involved in other components. Although the system is not explicitly
for trading, a retail user can translate these alerts into buy/sell decisions, hence
presenting them clearly is critical. This panel would be a simplified version of the MVP's “alert system with explanations,” showing only the main alerts relevant to
retail, with understandable text and avoiding overly technical details.

• Interactive Asset Table: A table that lists key assets or nodes with their main metrics (e.g., name, group, Composite Risk Index (CRI), Systemic Influence Score (SIS), recent volatility, etc.). This table can support sorting and simple filters. For example, the user could sort by SIS to see which assets are currently the most systemically influential (the whitepaper mentions identifying “which 50–100 assets concentrate the greatest potential impact on the system.”¹⁰). They can also filter by group or search for a specific asset. Each row could be expanded for more details or actions (such as a “view chart” button that focuses the network view on that asset). To avoid overwhelming the retail user, the table would initially display the most important fields and hide advanced filtering options that a professional might have.

• Volatility and Time Trend Charts: Various charts to visualize the evolution of certain metrics over time. A key example is a timeline chart of the volatility or composite risk index of an asset or sector over weeks/months.

The timeline of events can also be overlaid with indicators of when alerts or macro events occurred (according to the timeline functionality of MVP 11). This helps the user contextualize alerts with historical events or regime changes. An advanced retail user might, for example, see the trend of a subsegment's CRI showing an anomalous increase over the last 3 weeks, supporting the issued alert. We will implement this component using line/area chart libraries (such as Chart.js, Recharts, or similar), with the option to toggle between metrics (volatility, risk, price if available, etc.). It will include basic zoom/pan and tooltips.

• Network visualization Correlations/Propagation: An interactive network graph that

shows the dependency and exposure relationships between assets, representing the causal
network architecture described in the system (collateral, derivation, etc. 12). For a retail user, this
could be a view that appears when selecting a critical asset: a subgraph would be displayed with
that asset at the center and its most relevant connections (immediate neighborhood in the network). Each
node could be colored by its current risk level or its role (bank, fund, vehicle, etc.), and
the edges labeled with the type of relationship (e.g., “collateral,” “exposure”). This network
allows for the intuitive visualization of possible contagion paths and is one of the central pieces

for answering questions such as “what happens if X falls? Who does it drag down?” 13. Since complex
networks can be overwhelming, for retail we will limit it to close levels and perhaps a
“summary” view. Technically, a library such as vis.js, Cytoscape.js, or D3-force can be used.

3

for graphs, with controls for dragging nodes, zooming, etc. This component corresponds to the

“network view” mentioned for the interactive dashboard 11.

• Stress simulator (scenarios): An interface that allows the user to simulate a hypothetical shock
to an asset or node and see how the stress might propagate through the system. According to the
whitepaper, the engine allows simulating shocks (hypothetical or observed) and user-defined scenarios
14. For advanced retail, we would provide a simple simulator: for example, a
form where the user chooses a key asset (or uses a predefined one marked as

“fragile”) and applies a shock (e.g., a 10% drop in its value, or the default). Upon execution, the frontend
will call an API endpoint that runs the stress propagation engine, and then
the results will be displayed visually: perhaps by highlighting on the network which nodes would be most
affected (by coloring them) and/or showing the changes in metrics in the table. A short text report of “Most Impacted Assets” could also be presented. This component would perform
a complex task but will focus on usability: simple presets (such as “simulate subprime crisis” or “interest rate shock +2%) could be available for retail users, while
professionals would have more granular controls. The simulator will be in line with the
“stress propagation with user-defined scenarios” functionality.

• Selected asset details panel: When the user selects a specific asset

(either by clicking on the table, the heatmap, or the network), the interface will display a panel with the
detailed information for that asset. There you will find its category, key metrics (current CRI, SIS, volatility, main connections, recent associated alerts), and perhaps comparisons with historical data. This is equivalent to the “asset panel” mentioned in dashboard 11. It can also include small thumbnail charts (sparklines of its risk over time, etc.) for quick context. This way, advanced retail traders can understand why an asset is marked as risky: see which variables have changed and what similarities there are with historical events, answering the question, “Why did a specific alert trigger?” with a simplified narrative.

• Event Timeline: A timeline component that displays notable events over time (e.g., rate hikes, bankruptcies, relevant news) and the alerts generated by the system over the past few months. This timeline, perhaps integrated into the overall dashboard or a group view, serves to correlate events with changes in risk. For example,

it can show that in a certain month, X alerts occurred, concentrated in a subgroup,

coinciding with an identifiable macro event. This is included in the core functionalities

11 and reinforces the explanatory nature of the platform. In the UI, it could be a time slider or

a timeline with interactive markers (using timeline libraries or simply a time series chart
with annotations).

All these components will be integrated into a main Dashboard that acts as a hub:
possibly a split-screen view where the global heatmap occupies the main space, alongside the
alerts table or panel, and with the ability to drill down into either of them (e.g., clicking on a
group in the heatmap filters the table to that group, or clicking on an asset opens its details and network). Since the
advanced retail user should have a simplified experience, the interface will prioritize displaying
relevant information immediately (overview first) and More specialized configurations or data will be revealed after additional interactions. This aligns with the philosophy of delivering a simplified and less configurable view to this role, reserving complexity for future Pro or institutional profiles.

4
JWT Authentication Integration
The application will include user authentication via JWT from the start, ensuring that only registered users can access the dashboard. The authentication flow will be as follows:

• Login Form: A /login page will be implemented with a form requesting credentials (e.g., email/username and password). Upon submission, the frontend will make a POST request to the REST API (/api/login or similar) with the credentials.

• JWT Reception and Secure Storage: If the credentials are valid, the backend will return a signed JWT (JSON Web Token) containing the user's identity and possibly authorization claims (roles, expiration, etc.). The frontend will then store
this token for use in subsequent requests. For security, it is recommended to store the
JWT in an HttpOnly cookie instead of localStorage, mitigating XSS risks. In
development, we could use localStorage or sessionStorage for simplicity, but for
production, we will opt for secure HttpOnly cookies with the access token. Additionally, the
backend will issue a long-lived Refresh Token, also stored in a separate cookie (HttpOnly).

This refresh token will allow obtaining new JWTs without requiring re-login when the
token expires, following the standard mechanism: the access JWT will have a short expiration (e.g., 1
hour), and upon expiration, the frontend will call a refresh endpoint using the refresh token to
receive a new JWT.
... • Session Management and Persistence: Once authenticated, the authentication state (logged-in user and their basic information) will be maintained in a global context or store. We will use, for example, a React AuthContext or a Zustand store to store that the user is authenticated and their data (name, role, etc.). If the user refreshes the page, the presence of the token (in a cookie or storage) will be checked, and if valid, the session will be restored automatically (even making a request to /api/me to obtain profile information if necessary). We will implement auto-refresh logic: before the JWT expires, or upon receiving a 401 Unauthorized code from the API, an attempt will be made to transparently exchange the refresh token for a new JWT.

• API Request Interception: We will configure a central HTTP client (e.g., Axios)

with a global interceptor that appends the JWT to the Authorization: Bearer <token> header

in every call to the protected API. This way, all data requests (e.g., retrieving data from the

heatmap, alerts, etc.) will automatically pass the token. If a response indicates token expiration

(e.g., 401 error code and a specific message), the interceptor can pause the request,

trigger the token refresh sequence to obtain a new JWT, and

retry the original request

with the new token, all without disturbing the user. This approach ensures that the user is not
kicked back to login due to short expirations and improves the seamless user experience.

• Frontend Route Protection: We will use Next.js' capabilities to protect
private pages. For example, we can implement middleware in Next 13+

(middleware.ts) that intercepts requests to pages in /dashboard and other internal routes,
checking for the existence of the JWT session cookie. If it is not present or is invalid, the user is
redirected to /login. Alternatively (or additionally), at the client-side
component level, when assembling private pages, we will also check the authentication context;

if the user is not logged in, we will use next/router to redirect them to login.

This provides optimistic verification on the client side and ensures that private routes are
not truly accessible without a valid token.

5

• Logout: A logout option will be provided which, when activated, will clear the client's authentication data.

This involves deleting the JWT (if it was in localStorage) or invalidating the cookie (setting the expiration date), as well as clearing the global user state in the app.

After logout, the user will be redirected to the login page. We will also notify the backend if it is necessary to invalidate the refresh token stored on the server.

With this JWT authentication architecture, we meet the robust authentication requirement mentioned in non-functional requirements 1. ensuring that each data request is authorized. The use of stateless JWT fits well with a frontend decoupled from the backend, allowing the backend to scale horizontally without in-memory sessions. Furthermore, it is a standard, lightweight system compatible with middleware in Next.js for route protection. Best practices considered include the use of HttpOnly cookies (to prevent XSS), inclusion of CSRF protection where appropriate (although with JWT this is usually mitigated using SameSite cookies), and session expirations/refreshes to avoid leaving sessions open indefinitely.

API Consumption Strategy and State Management
The application will need to handle a significant amount of state: data from the API (server state) such as risk metrics for multiple assets, and internal UI state (such as which asset is selected, filter options, etc.). To address this efficiently and maintainably, we will follow a hybrid strategy:

• React Query (formerly React Query) for asynchronous server data: We will use React Query for REST API requests, as it acts as a global asynchronous state manager specializing in fetching/caching. With React Query, we will define queries to, for example, retrieve the alert list, obtain the risk heatmap, details of an asset, etc., each identified by a query key. This library offers us multiple benefits:

• Automatic caching and synchronization: The data for each query is cached in memory. If multiple components need the same information, React Query avoids duplicate calls and provides them with the cached or refreshed data only once. For example, if the alert panel and the dashboard require the list of active alerts, the HTTP request will only be made once, and both components will share the response.

• Loading/error state handling: The library exposes states like `isLoading`, `isError`, etc., simplifying the logic in components for displaying spinners or error messages without writing a lot of boilerplate code.

• Automatic refetching and stale-while-revalidate: We can configure queries to be updated in the background at regular intervals or upon reconnection, ensuring fresh data. React Query follows the "stale data is better than nothing" principle, displaying cached data immediately and revalidating in the background, providing a smooth user experience.

• Mutations with cache updates: For actions such as acknowledging/dismissing an alert or saving a configuration, React Query allows defining mutations and optimistically updating the local cache.

• DevTools: In development, we can leverage React Query DevTools to view the state of each query and easily debug.

All of this saves us from having to manually manage load states or implement redux-thunk/
sagas for each call. React Query has become a standard solution for server state in React and will help us scale as the number of endpoints increases.

• Global client (UI) state: For state that is purely interface-related or does not originate from the server, we will adopt a lightweight solution centered on Zustand or the Context API.

6

Examples of this type of state include: the currently selected asset, display preferences (dark mode enabled or disabled, units), filters applied to tables, etc.

These states do not justify a heavyweight solution.

Zustand is a very lightweight, fast, and scalable library for handling global state, based on hooks, which allows us to define simple stores without ceremony (it does not require additional providers, unlike Redux).

With Zustand, we can create a global store with slices for different contexts, e.g. A slice of useUIStore

for dark mode and active selected, another useFilterStore for filters, etc., and the
components consume these hooks. The syntax is very concise and eliminates a lot of boilerplate

compared to Redux, making development more agile.

Alternatively, for certain local states we could simply use React's Context +

useReducer or useState to elevate state, if they are trivial. For example, a context for the theme

(dark/light) or a context for the current selection might suffice. However, Zustánd gives us
a more structured pattern without being complex, so it's a good choice given that the application

may grow in functionality.

• Redux Toolkit? Since the question mentions it, it's worth noting that Redux
won't be used initially because it would add unnecessary complexity at this point. Redux Toolkit is excellent

for large projects with very complex state and a need for tools Advanced tools

(middleware, devtools, etc.), but in an initial application it is preferable to avoid this overhead if it is not
required 24 25. In general, Redux is suitable when a single, highly structured global state is needed
and the app is large enough or worked on by many developers 24.
Here we will adopt a more agile approach: React Query will handle all remote data state
with its caches (which in itself acts as a global store for said data), and for global UI state
we use a minimalist library (Zustan) or contexts. This covers our
needs without sacrificing scalability, since Zustand is perfectly suitable even in large apps
while maintaining excellent performance 26.

In short, state management will be divided into server state vs. client state. React Query
handles the former (optimized API queries, consistent caching throughout the app 21), while
for the latter we have simple tools that prevent over-engineering. This strategy follows the modern recommendation to use Redux only when a very complex global state is truly needed, favoring simpler solutions in moderately sized projects.

Furthermore, we will organize API access in a central service module (features/shared/services/api.ts, for example) where we will configure an Axios object or fetch wrapper. This module will contain methods such as `api.fetchHeatmap()` or `api.fetchAssetDetails(id)`, which internally perform GET requests to the corresponding routes and handle the token (perhaps leveraging the interceptor mentioned in the authentication section). React Query will use these methods in its `queryFn`. This way, if the base URL changes or common headers need to be added, it's all centralized.

Finally, to ensure separation of responsibilities, the React component will not call fetch directly but will instead use custom hooks provided by React Query (e.g., a useHeatmapData() hook that encapsulates useQuery('heatmap', api.fetchHeatmap)). This improves maintainability and facilitates testing, as we can easily mock the API service functions in tests instead of simulating actual fetching.

7
Visual Design System and UX Consistent with the Whitepaper
The visual interface will follow a professional and modern FinTech design, aligned with the serious and technical tone of the whitepaper. The following design considerations are described:

• Professional color palette: Colors that convey trust and seriousness, common in the financial sector, will be chosen (blue tones, dark grays, blacks, and accents in controlled warm colors to highlight alerts). For example, navy blue or graphite gray for
backgrounds, and accents in orange/amber or red to highlight high risk levels, green for
positive signs or recovery, etc. This palette should be understated; we will avoid overly
saturated colors that detract from credibility. Furthermore, color conventions will be taken into account:

green is usually associated with upswings/improvements, red with downswings/risk, which aligns with the idea of
heatmaps and buy/sell signals. We will ensure that the palette reflects the personality of the
WallStreetWar brand and its target audience, conveying an “advanced fintech” style:

elegant and technical, similar to that of professional trading platforms or financial analysis tools.

• Dark and Light Modes: An optional Dark Mode will be implemented from the outset. Many
financial dashboards and charting tools offer a dark mode because it reduces eye strain
when analyzing data for extended periods and enhances data visualizations.

By default, we could use a professional light theme (light background with dark text) and allow
the user to switch to a dark theme (dark background, light text). We will use a

theming system (e.g., CSS variables or ThemeProvider context) to define both palettes.
Each color in the palette will have its variant in light and dark modes, ensuring brand consistency
in both modes. Attention will be paid to ensuring that the colors have sufficient contrast
in both modes; for example, in dark mode, backgrounds will be very dark gray instead of pure black
to avoid excessive contrast, and text will be off-white, etc. The versatile design will ensure
that the interface looks good under different conditions.

Graphics in dark mode will use
dark backgrounds and adapted default colors (e.g., slightly brighter colors or colors changed to
stand out against a dark background).

• Typography and Iconography: We will use a clean and legible typeface, probably sans-serif (e.g., Inter, Roboto, or Open Sans), with clear size hierarchies for titles. Text, subtitles, base text, and chart annotations. The minimum font size will be chosen to facilitate the reading of complex numerical data without straining the eyes. Including a monospaced font for numerical values ​​in tables can be useful for aligning figures. Icons will be used consistently: for example, an alert icon (triangle) for alerts, up/down arrows to indicate trends, padlock icons to indicate secure sections, etc. We can use icon libraries (Material Icons, FontAwesome) with a linear and simple style, avoiding highly ornate icons.

• General UI Style: The style will be minimalist and data-oriented. Flat backgrounds, without unnecessary decorations, to give prominence to visualizations and tables. Modern flat design principles will be followed, with a touch of subtle neumorphism in containers if appropriate, but prioritizing functionality. Interactive components (buttons, toggles, dropdowns) will have styles consistent with the color palette: likely primary buttons in dark blue/gray, dangerous action buttons in red, etc., always maintaining consistency. A small internal design system will be designed to reuse UI components with homogeneous styles. For example, a Card or Panel container component will have the same style of soft rounded edges and light shadow everywhere elements are grouped.

8

• Consistency with the whitepaper: Although the whitepaper is technical, we draw conceptual inspiration from it: it is a "financial system radar" that provides early warning signals. The interface should reflect this radar/early warning idea in its aesthetics: for example, it could have amber accents that allude to early warnings, or use visual radar metaphors (such as highlighted points on a map). Also, the UI should be explainable; This influences the design: we will add help icons or tooltips to charts that, when hovered over or clicked, display the explanation/narrative behind the alert or metric. This ensures that each visualization has context for the user (satisfying the need for explainability mentioned in UI 1 requirements).

• Accessibility and contrast: Given the professional profile of the tool, we do not want to exclude users; we will ensure that color contrasts meet standards (at least WCAG AA) for text and charts. Text contrast on a light or dark background will be checked for readability. We will also use indicators beyond just color for critical elements (for example, adding "High Risk" icons or labels in addition to red, for users with color blindness). Responsive design will be considered to some extent: the application will likely be used on large screens (desktops) due to the complexity of the data, but it must at least be usable on tablets. Flexbox and CSS Grid will be used to create a fluid layout that can collapse or expand; perhaps a collapsible sidebar menu for more space on small screens.

• UI Libraries: To speed up development while maintaining visual consistency, a UI component framework like Material-UI (MUI) or Ant Design can be used, but with customization. For example, MUI provides readily available components with integrated theming (making it easy to toggle dark mode), and we could apply our custom theme on top (colors and styles tailored to our branding). This ensures uniformity in details like tooltips, dialogs, etc., without starting from scratch. If a more unique style is desired, we could opt to create custom components using Styled Components or CSS Modules with our color palette. Another intermediate option is Chakra UI, which is well-suited for dashboards and has native dark mode support, allowing us to define color tokens for different levels. Whatever the base, a consistent design system will be defined: uniform spacing, font sizes, standard borders and shadows, etc., documented so that all developers follow the same style in new components.

In short, the visual experience will be that of an advanced financial tool: dark, elegant, information-dense yet clear in presentation. The advanced retail user should feel they are using a serious, almost professional-level platform, but at the same time not intimidating. Consistency and simplicity within complexity are the goal: a lot of visual content, but organized and coded with color and design to facilitate its assimilation.

Testing considerations (unit and end-to-end testing)
Given the criticality of the financial data presented We will emphasize quality through automated testing. We will implement both unit tests for components/logic and end-to-end tests that cover the main user flows.

• Unit and integration tests (components): We will use Jest as our testing framework, along with the React Testing Library (RTL) to focus testing on the behavior of components as the user interacts with them. Unit tests are essential to ensure quality and prevent regressions in production. Tests will be created for key components: for example, verifying that the Login component displays the form correctly and reacts to the submit (by mocking the login call), or that the Heatmap renders the correct cells given simulated data. With RTL, we will simulate interactions: clicks, inputs, etc., and assert results in the DOM (for example, "when clicking on an asset in the table, the details panel displays the correct name"). We will also test the logic of our custom hooks (e.g., a useAuth hook that handles login/logout) using context mocks or fetch implementation mocks.

To isolate the testing of components that depend on API data, we will use mocks. For example, when testing the entire Dashboard, we could use Mock Service Workers (MSW) to simulate REST API responses (such as sample data for the heatmap or alerts) without making actual requests. This allows us to verify that our UI handles different scenarios well: API returns valid data, or API returns an error (do we display an error message to the user?). Similarly, we will test edge cases: what happens if there is no data (e.g., an empty table; "No assets to display" should be displayed), etc.

We will keep the tests organized in a structure parallel to the code (e.g., tests within each feature, or *.test.tsx files alongside each component). We will aim to cover a significant portion of the critical functionality. One goal will be to achieve a reasonable code coverage percentage (we can measure this with Jest --coverage) to ensure we don't leave any areas untested, although we will focus more on covering functionalities than on chasing a specific number.

• End-to-end (E2E) testing: To validate complete user flows, we will use a tool like Cypress or Playwright. Cypress has the advantage of running in a controlled browser environment with good visual feedback, ideal for testing our application locally in a Docker or development environment. We will write E2E scenarios such as: "The user can log in successfully and see the dashboard," "Stress simulation produces expected results in the UI," "The dark mode toggle changes the background and text styles," etc. These tests will launch the live app (deployed locally) and automate a browser to interact with the interface: filling out forms, clicking buttons, navigating between pages, and verifying that certain elements appear or change state.

A critical end-to-end (E2E) scenario would be, for example: "Detailed Alert Flow" – Log in, verify that the heatmap loads with colored cells, click on the highest-risk cell, verify that the table filters assets from that segment, click on an asset in the table with an alert, verify that navigation (or a modal opens) is possible with the network of that asset and the alert explained. This type of test ensures that the integrated components work correctly together and that the app meets the end-to-end business expectations.

To facilitate E2E testing, we can start a mock backend (or stub endpoints) with predictable data, so that the tests do not depend on live data (for example, using MSW in server mode, or a flag in the API to serve static demo data). We will also consider timing: Cypress allows waiting for certain requests to complete or for elements to appear; we will use this to synchronize with our asynchronous calls.

• Performance and Security Testing: Additionally, although manually at the beginning, we will
monitor the app's performance. Tools like Lighthouse or React profiles will help us
detect rendering bottlenecks (important if the network has
many nodes, etc.). Regarding security, we will perform basic penetration tests in the
QA phase: ensuring that the dashboard cannot be accessed without a token, that HttpOnly cookies are
not accessible via JS, etc. For this, we could write E2E tests that verify, for example,
that an unauthenticated user is redirected if they try to force the dashboard URL.

10

In summary, we will adopt a testing culture from the outset. Initially, integrate it into the development flow (running npm tests on every commit, and perhaps setting up a CI pipeline that runs the suite automatically on every push). This will ensure the application remains stable and reliable as it evolves, which is essential in a fintech product where errors could lead to ill-informed financial decisions.

Suggestions for local deployment and future scaling: In the initial phase, the application should run locally in both a "pure" development environment and Docker to facilitate a smooth production deployment:

• Local (pure) development environment: Thanks to Next.js, starting the dev environment is easy with `npm run dev` or `yarn dev`, which starts the development server with Hot Module Reload (HMR) to instantly reload changes. During development, it is recommended to use this native mode since it offers faster reload speeds and better DX, while Docker could add some unnecessary overhead. Each developer can run the app locally (making sure they have Node.js installed, ideally the same version defined in package.json/.nvmrc). We will configure .env.development environment files with the necessary variables, for example, the API URL (which locally can be http://localhost:8000 if there is a local backend) and the OAuth credentials if any (not applicable now). Next.js allows access to public variables (prefixed with NEXT_PUBLIC_) for, say, the base API URL, which we can adjust according to the environment.

• Local environment with Docker: We will provide a Dockerfile for the frontend that allows the app to run in an isolated container. This ensures that "it works on my machine" is consistent for everyone and prepares the ground for deployment to servers. The Dockerfile for development can use a base Node image (for example, node:18-alpine), copy the code, install dependencies, and run `npm run dev`. We can even use Docker Compose to orchestrate the frontend and backend together locally: one service for the API (for example, a Python/Node/Java Spring container with its database) and another for the frontend, so that with a single `docker-compose up` command, the entire stack is up. In Compose, we'll configure ports (the frontend typically on 3000, the backend on 8000, etc.) and mount volumes so that changes in the host code are reflected within the container (useful for iterative development).

To optimize the experience, a separate configuration could be maintained for development versus production in Docker Compose. In fact, Next.js warns that using Docker in development can sometimes be slower than native execution, so we might recommend Docker more for CI or embedded testing environments than for the developer's day-to-day work, unless they cannot install Node locally.

• Production Deployment: When it's time to deploy, the app can be built with `npm run build`, resulting in an optimized package. If we are using Next.js with server-side features (such as middleware or API routes), we will likely deploy the application as a Node server unit. In production, we will use Docker to package the pre-compiled application: a multi-stage Dockerfile that first installs dependencies and generates the static build, and then uses a lightweight image (node:alpine) to serve the result (Next.js needs a Node server for SSR unless we export statically). The resulting image can be deployed on any service (AWS ECS, Azure, Heroku, etc., or platforms like Vercel that directly support Next).

11
It's important to externalize sensitive or specific environment variables during deployment (for example, the production API URL, keys for Sentry or other tools if added, etc.). To do this, we'll use `.env.production` or variables in the container environment. We'll ensure that the API configuration is easily switchable: perhaps with the `NEXT_PUBLIC_API_URL` variable pointing to `https://api.wallstreetwar.com` in production versus `http://localhost:8000` in development.

• Docker Compose for production: If the final solution runs entirely in Docker (API, Frontend, database), a Compose (or better yet, Kubernetes YAML) can be used for production. However, the frontend itself would likely be deployed on a frontend service (e.g., Vercel, Netlify, or hosted in a container on a VM). In any case, the fact that it was developed with containers in mind ensures there won't be any "it works locally but not on the server" surprises.

• Additional tools: See We could include a set of convenient scripts in the repository, for example, one to initialize test data (in case we don't have a real backend and we serve static JSON). It's also worth mentioning that Next.js 13+ with App Router supports edge features; if we wanted to deploy on Vercel (an edge network) in the future, we could migrate certain middleware to run on the edge network for performance. But initially, a simple Node container will suffice.

In conclusion, for local environments, we recommend developers use `npm run dev` for simplicity and speed, and we maintain Docker/Compose files to ensure environment parity and facilitate the transition to production. Scalability is guaranteed: the modular React/Next architecture and the use of containers will allow us to scale horizontally (multiple frontend instances behind a load balancer) as the user base grows, without code changes.

Reference: Next.js' official guidelines suggest using Docker primarily for production deployments, while maintaining local reload speeds. Following this, we will leverage Docker for CI/CD and production, but maintain an optimal developer experience locally.

With all of the above, the proposal covers the main requested aspects: a well-planned frontend architecture with Next.js, a modularly organized project, critical UI components inspired by the WallStreetWar engine, secure JWT authentication, efficient API consumption with modern state management, a visual design appropriate for the fintech domain, tests to ensure quality, and a deployment strategy that facilitates starting locally and scaling to production. This foundation will allow for the subsequent incorporation of different views for professional and institutional users in an orderly manner, adhering to the roadmap outlined in the whitepaper. Every technical and design decision aims to make WallStreetWar Frontend fast, secure, and explainable, providing advanced retail users with a powerful yet accessible tool to anticipate risks in the financial system.
