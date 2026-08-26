# Madrid Dataset

Madrid Dataset and downstream urban analytics dataset based on Madrid open data.

## Installation

Clone this repository to a local working folder.

A python package manager and an IDE such as `vscode` are recommended.

### UV

The UV package manager can be installed on mac per `brew install uv`. Packages can then be installed into a virtual environment per `uv sync`.

### PDM

The PDM package manager can be installed on mac per `brew install pdm`. Packages can then be installed into a virtual environment per `pdm install`.

### IDE and venv

The virtual environment should be detected automatically by IDEs such as vscode, else activate it manually.

### Setup

Create a `temp` folder inside the repository's root folder. This folder is ignored by `.gitignore` but is necessary for the script to output files from the processing steps.

The code is in `process/compute.py` file and can be run using code cells demarcated by the `# %%` lines (assuming an IDE such as vscode). Else these can be copied and pasted into a Python Notebook.

The file can otherwise be run directly, though the file paths to the `data` folder may need to be adjusted (e.g. changing `../` to `./`).

## Generated dataset columns

The processing script writes `temp/dataset.gpkg` (and a central-districts subset, `temp/dataset_subset.gpkg`). All network measures are computed with cityseer 5.8.0 through the `CityNetwork` API. The street network is analysed as a dual graph: each row of the dataset is one street segment, represented internally as a dual graph node placed at the segment midpoint. Only live nodes (segment midpoints inside the city boundary) that fall within a named district are saved. Numeric columns are stored as float32.

### Notation

- $i$, $j$, $s$, $t$ index street segments (dual graph nodes). Row $i$ holds the measures for segment $i$.
- $w_j$ is the length in metres of street segment $j$ (the `seg_length` column).
- $d_{ij}$ is the shortest network path distance in metres between the midpoints of segments $i$ and $j$, measured along the street network.
- $a_{ij}$ is the cumulative angular change in degrees along the simplest (minimum angular change) route between $i$ and $j$. The metric length of that route is $m_{ij}$.
- $d_{max}$ is the distance threshold: one column per $d_{max} \in \{200, 500, 1000, 2000, 5000, 10000\}$ metres for centralities, and $d_{max} \in \{100, 200, 500, 1000, 2000\}$ for land-use measures.
- $\beta = 4 / d_{max}$ is the decay constant paired with each threshold, so that $\exp(-\beta d) = 0.0183$ at $d = d_{max}$.
- Metric measures aggregate over $R_i = \{j \neq i : d_{ij} \leq d_{max}\}$. Angular measures aggregate over $R^{ang}_i = \{j \neq i : m_{ij} \leq d_{max}\}$; the threshold applies to the metric length of the angularly simplest route, and the routing cost is angular.

### Shortest path (metric) centralities

Computed by `CityNetwork.centrality_shortest`. Unweighted columns count segments; length-weighted (`cc_lw_*`) columns weight each reachable segment by the street length it represents, applied at the destination.

| Column | Formula |
| --- | --- |
| `cc_density_{d}` | $\sum_{j \in R_i} 1$ |
| `cc_farness_{d}` | $\sum_{j \in R_i} d_{ij}$ |
| `cc_harmonic_{d}` | $\sum_{j \in R_i} 1 / d_{ij}$ |
| `cc_beta_{d}` | $\sum_{j \in R_i} \exp(-\beta d_{ij})$ |
| `cc_hillier_{d}` | `cc_density`$^2$ / `cc_farness` |
| `cc_cycles_{d}` | circuit rank (count of independent cycles) of the subgraph reachable within $d_{max}$ |
| `cc_betweenness_{d}` | $\sum_{\{s,t\}} \sigma_{st}(i) / \sigma_{st}$ |
| `cc_betweenness_beta_{d}` | $\sum_{\{s,t\}} \exp(-\beta d_{st}) \, \sigma_{st}(i) / \sigma_{st}$ |
| `cc_lw_density_{d}` | $\sum_{j \in R_i} w_j$ (total reachable street length) |
| `cc_lw_farness_{d}` | $\sum_{j \in R_i} w_j d_{ij}$ |
| `cc_lw_harmonic_{d}` | $\sum_{j \in R_i} w_j / d_{ij}$ |
| `cc_lw_beta_{d}` | $\sum_{j \in R_i} w_j \exp(-\beta d_{ij})$ |
| `cc_lw_hillier_{d}` | `cc_lw_density`$^2$ / `cc_lw_farness` |
| `cc_lw_betweenness_{d}` | $\sum_{\{s,t\}} w_s w_t \, \sigma_{st}(i) / \sigma_{st}$ |
| `cc_lw_betweenness_beta_{d}` | $\sum_{\{s,t\}} w_s w_t \exp(-\beta d_{st}) \, \sigma_{st}(i) / \sigma_{st}$ |

Betweenness convention: the sums run over unordered pairs $\{s, t\}$ with $s \neq i$, $t \neq i$, and $d_{st} \leq d_{max}$. $\sigma_{st}$ is the number of shortest paths between $s$ and $t$ (paths within the solver's floating point tolerance of the best cost count as equal), and $\sigma_{st}(i)$ is the number of those passing through $i$ as an intermediate node; endpoints receive no credit for their own pairs. Pairs are counted wherever both endpoints lie in the buffered analysis extent, so routes that enter and leave the boundary, including routes between two buffer locations that pass through it, contribute. In the length-weighted variants each pair is weighted by the product $w_s w_t$ of the endpoint segment lengths.

### Simplest path (angular) centralities

Computed by `CityNetwork.centrality_simplest`; columns carry the `_ang` suffix. Routing minimises cumulative angular change on the dual graph, with the Space Syntax convention that maps $0$ to $180$ degrees onto $0$ to $2$ (a scaling unit of 90).

| Column | Formula |
| --- | --- |
| `cc_density_{d}_ang` | $\sum_{j \in R^{ang}_i} 1$ |
| `cc_farness_{d}_ang` | $\sum_{j \in R^{ang}_i} a_{ij} / 90$ |
| `cc_harmonic_{d}_ang` | $\sum_{j \in R^{ang}_i} 1 / (1 + a_{ij} / 90)$ |
| `cc_hillier_{d}_ang` | `cc_density_ang`$^2$ / `cc_farness_ang` |
| `cc_betweenness_{d}_ang` | $\sum_{\{s,t\}} \sigma^{ang}_{st}(i) / \sigma^{ang}_{st}$ |
| `cc_lw_density_{d}_ang` | $\sum_{j \in R^{ang}_i} w_j$ |
| `cc_lw_farness_{d}_ang` | $\sum_{j \in R^{ang}_i} w_j a_{ij} / 90$ |
| `cc_lw_harmonic_{d}_ang` | $\sum_{j \in R^{ang}_i} w_j / (1 + a_{ij} / 90)$ |
| `cc_lw_hillier_{d}_ang` | `cc_lw_density_ang`$^2$ / `cc_lw_farness_ang` |
| `cc_lw_betweenness_{d}_ang` | $\sum_{\{s,t\}} w_s w_t \, \sigma^{ang}_{st}(i) / \sigma^{ang}_{st}$ |

The betweenness convention matches the metric case, with $\sigma^{ang}_{st}$ counting angularly simplest routes whose metric length is within $d_{max}$, and near-equal angular costs (within the solver tolerance) treated as ties.

### Land-use measures

Computed by `CityNetwork.compute_accessibilities` and `CityNetwork.compute_mixed_uses` from the cleaned premises data (`division_desc` categories). Premises are assigned to the network within a maximum assignment distance of 100 m, and $d_k$ denotes the network distance from segment $i$ to premise $k$ including the assignment offset. Angular variants (`_ang`) route by minimum angular change with the same aggregation formulas. $\beta = 4 / d_{max}$ as above.

| Column | Formula |
| --- | --- |
| `cc_{key}_{d}_nw` | $\sum_{k \in K, d_k \leq d_{max}} 1$, the count of reachable premises of category $key$ |
| `cc_{key}_{d}_wt` | $\sum_{k \in K, d_k \leq d_{max}} \exp(-\beta d_k)$ |
| `cc_{key}_nearest_max_2000` | $\min_k d_k$, the network distance to the nearest premise of category $key$ within the largest threshold (2000 m) |
| `cc_hill_q{q}_{d}_wt` | distance-weighted Hill diversity of order $q$ over the reachable premises, see below |

Weighted Hill diversity follows the branch-weighted formulation: with $N_a$ the count of reachable premises of class $a$, $p_a = N_a / \sum_b N_b$, $d_a$ the network distance to the nearest reachable premise of class $a$, $u_a = \exp(-\beta d_a)$, and $T = \sum_a u_a p_a$,

$$D_q = \Big( \sum_a u_a (p_a / T)^q \Big)^{1/(1-q)} \quad (q \neq 1), \qquad D_1 = \exp\Big( -\sum_a \frac{u_a p_a}{T} \ln \frac{u_a p_a}{T} \Big).$$

### Other columns

| Column | Description |
| --- | --- |
| `index` | dual graph node key, formed from the primal end node keys and edge index |
| `ns_node_idx` | internal cityseer node index |
| `x`, `y` | segment midpoint coordinates (EPSG:25830) |
| `live` | midpoint lies inside the city boundary (all saved rows are live) |
| `seg_length` | street segment length in metres ($w$ above); named `weight` in builds before cityseer 5 |
| `primal_edge_node_a`, `primal_edge_node_b`, `primal_edge_idx` | primal end node keys and edge index |
| `dual_node` | segment midpoint as WKT |
| `bearing` | bearing in degrees between the segment end points |
| `district`, `neighb` | district and neighbourhood containing the segment centroid |
| `pop_dens` | GHS-POP population density at the midpoint, per km² |
| `clased`, `nombre` | road class and street name carried from the IGN source data |
| `geometry` | the primal street segment LineString, simplified to 2 m tolerance |

## Data Sources

### Madrid Data

The data sources are pre-processed as described below and saved to the `data` sub-folder in this repository so that the datasets and results can be reproduced in downstream research.

#### Premises Data

- Source:
  - [Download activities dataset](https://datos.madrid.es/portal/site/egob/menuitem.c05c1f754a33a9fbe4b2e4b284f1a5a0/?vgnextoid=66665cde99be2410VgnVCM1000000b205a0aRCRD&vgnextchannel=374512b9ace9f310VgnVCM100000171f5a0aRCRD&vgnextfmt=default)
  - [License](https://datos.madrid.es/egob/catalogo/aviso-legal): Open data under Spanish Law 37/2007 on Reuse of Public Sector Information.
  - Cite: _Origin of the data: Madrid City Council (or, where appropriate, administrative body, agency or entity in question)._
  - Description: _Microdata file of the census of premises and activities of the Madrid City Council, classified according to their type of access (street door or grouped), situation (open, closed...) and indication of the economic activity exercised and the hospitality and restaurant terraces that appear registered in said census._
- Premises pre-processing:
  - Import CSV and export as GPKG in EPSG:25830
  - Remove locations without eastings and northings
  - Delete attribute columns where not describing census units or landuse identifiers. (See `compute.py` column renaming for retained columns.)
  - Save as GPKG
  - Vacuum

#### Madrid Neighbourhoods

- Source:
  - [Download](https://datos.madrid.es/portal/site/egob/menuitem.c05c1f754a33a9fbe4b2e4b284f1a5a0/?vgnextoid=760e5eb0d73a7710VgnVCM2000001f4a900aRCRD&vgnextchannel=374512b9ace9f310VgnVCM100000171f5a0aRCRD&vgnextfmt=default)
  - [License](https://datos.madrid.es/egob/catalogo/aviso-legal)
  - Cite: _Origin of the data: Madrid City Council (or, where appropriate, administrative body, body or entity in question)_
  - Description: _Delimitation of the 131 neighborhoods of the municipality of Madrid. The names and codes of each neighborhood and the districts to which they belong are indicated. The initial delimitation corresponds to the territorial restructuring of 1987._
- Save to GPKG in EPSG:25830
- Create buffered boundary
  - Buffer by 20km and dissolve
  - Delete attribute columns
  - Export to GPKG

#### Street Network (Red Viaria)

- Source:
  - [Download](https://centrodedescargas.cnig.es/CentroDescargas/index.jsp) (CNIG/IGN - Redes de Transporte - Madrid province)
  - [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/legalcode.es) ([ign.es](https://www.ign.es))
  - Cite: Attribute IGN (Instituto Geográfico Nacional de España).
  - Description: _Road network (Red Viaria) for Madrid province from the CNIG/IGN Redes de Transporte dataset. Layer `rt_tramo_vial` containing road segments with classification, surface, lane, and naming attributes._
- Street Network Pre-processing:
  - Download `RT_MADRID_gpkg.zip` from CNIG Centro de Descargas
  - Extract `red_viaria.gpkg`, layer `rt_tramo_vial`
  - Reproject from EPSG:4258 to EPSG:25830
  - Clip to 20km buffered bounds
  - Retain `clased` (road class) and `nombre` (road name) attributes only
  - Set coordinate grid precision to 1m and simplify geometries to 1m tolerance
  - Save as GPKG
  - Vacuum

#### Population Data

- Source:
  - [Download](https://ghsl.jrc.ec.europa.eu/download.php?ds=pop)
  - Citation: Schiavina M., Freire S., Carioli A., MacManus K. (2023): GHS-POP R2023A - GHS population grid multitemporal (1975-2030). European Commission, Joint Research Centre (JRC).
  - Description: _The spatial raster dataset depicts the distribution of residential population, expressed as the number of people per cell._
- Pre-processing:
  - `gdalwarp -cutline buffered_bounds.gpkg -crop_to_cutline -of GTiff -co "COMPRESS=LZW" -dstnodata -200 -t_srs EPSG:25830 population.tif population_clipped.tif`

#### Pedestrian Count Data

> No longer used.

- [Download](https://datos.madrid.es/portal/site/egob/menuitem.c05c1f754a33a9fbe4b2e4b284f1a5a0/?vgnextoid=695cd64d6f9b9610VgnVCM1000001d4a900aRCRD&vgnextchannel=374512b9ace9f310VgnVCM100000171f5a0aRCRD&vgnextfmt=default)
- [License](https://datos.madrid.es/egob/catalogo/aviso-legal)

### Additional Potential Data Sources

- [Traffic counts](https://datos.madrid.es/sites/v/index.jsp?vgnextoid=fabbf3e1de124610VgnVCM2000001f4a900aRCRD&vgnextchannel=374512b9ace9f310VgnVCM100000171f5a0aRCRD)
- [Traffic intensity](https://datos.madrid.es/portal/site/egob/menuitem.c05c1f754a33a9fbe4b2e4b284f1a5a0/?vgnextoid=23d57fa19bfa7410VgnVCM2000000c205a0aRCRD&vgnextchannel=374512b9ace9f310VgnVCM100000171f5a0aRCRD)
- [Traffic data history](https://datos.madrid.es/portal/site/egob/menuitem.c05c1f754a33a9fbe4b2e4b284f1a5a0/?vgnextoid=33cb30c367e78410VgnVCM1000000b205a0aRCRD&vgnextchannel=374512b9ace9f310VgnVCM100000171f5a0aRCRD&vgnextfmt=default)
- [Traffic measurement points](https://datos.madrid.es/sites/v/index.jsp?vgnextoid=ee941ce6ba6d3410VgnVCM1000000b205a0aRCRD&vgnextchannel=374512b9ace9f310VgnVCM100000171f5a0aRCRD)
- [Pedestrian and bicycle counts](https://datos.madrid.es/sites/v/index.jsp?vgnextoid=d7d67271481e1610VgnVCM1000001d4a900aRCRD&vgnextchannel=374512b9ace9f310VgnVCM100000171f5a0aRCRD)
