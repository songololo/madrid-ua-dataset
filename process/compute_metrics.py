# %%
"""
Extracts:
- population density
- network centralities in metric, angular, and length weighted forms
- landuse access in metric, angular, mixed use form from premises data

Computed with cityseer 5.8.0 via the CityNetwork API. The exact formula for every
cc_* column is documented in README.md ("Generated dataset columns").
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
from cityseer.network import CityNetwork
from cityseer.tools import graphs, io, util
from rasterio import MemoryFile
from rasterstats import point_query
from shapely import geometry
from tqdm import tqdm

from process import premises_lu_schema

# update the paths to correspond to your file locations if different to below
# create a temp folder if not existing before running
PATH_STREETS = "./data/street_network.gpkg"
PATH_NEIGHBOURHOODS = "./data/neighbourhoods.gpkg"
PATH_OUT_DATASET = "./temp/dataset.gpkg"
PATH_OUT_DATASET_SUBSET = "./temp/dataset_subset.gpkg"
PATH_PREMISES = "./data/premises_activities.gpkg"
PATH_OUT_PREMISES = "./data/premises_clean.gpkg"
PATH_POPULATION = "./data/population_clipped.tif"

CENT_DISTANCES = [200, 500, 1000, 2000, 5000, 10000]
LU_DISTANCES = [100, 200, 500, 1000, 2000]

# metric (shortest path) centrality measures; c is metric distance, p = c / d_max
SHORTEST_CLOSENESS = {
    "density": "1",
    "farness": "c",
    "harmonic": "1/c",
    "beta": "exp(-4 * p)",
}
SHORTEST_BETWEENNESS = {
    "betweenness": "1",
    "betweenness_beta": "exp(-4 * p)",
}
# angular (simplest path) measures; c is cumulative angular change in degrees,
# scaled per the Space Syntax convention where 0 - 180 degrees maps to 0 - 2
SIMPLEST_CLOSENESS = {
    "density": "1",
    "farness": "c / 90",
    "harmonic": "1 / (1 + c / 90)",
}
SIMPLEST_BETWEENNESS = {
    "betweenness": "1",
}


def prefix_labels(exprs: dict[str, str]) -> dict[str, str]:
    return {f"lw_{k}": v for k, v in exprs.items()}


# %%
# open streets
edges_gdf = gpd.read_file(PATH_STREETS)
# convert multipart geoms to single
edges_gdf_singles = edges_gdf.explode(ignore_index=True)
# generate networkx; primal cleaning matches earlier builds of this dataset
G_nx = io.nx_from_generic_geopandas(edges_gdf_singles)
# removes degree 2 if found
G_nx = graphs.nx_remove_filler_nodes(G_nx)
G_nx = graphs.nx_remove_dangling_nodes(G_nx)

# %%
# city boundary
bounds = gpd.read_file(PATH_NEIGHBOURHOODS)
bounds_union_geom = bounds.buffer(10).geometry.union_all()

# %%
# build the dual graph network; cleaning is disabled because the primal graph
# above is already cleaned, so the graph passes through unchanged
cn = CityNetwork.from_nx(
    G_nx,
    boundary=bounds_union_geom,
    remove_fillers=False,
    remove_danglers=0,
    merge_parallel_dist=0,
)
nodes_gdf = cn.nodes_gdf

# %%
# primal street geometries (one LineString per dual node) for bearings and joins
primal_gdf = cn.to_geopandas()
# extract edge bearings for visualisation
nodes_gdf["bearing"] = [
    util.measure_bearing(
        np.array(line.coords[0][:2]),
        np.array(line.coords[-1][:2]),
    )
    for line in primal_gdf.geometry
]
# copy neighbourhood identifiers to nodes
primal_centroids_gdf = gpd.GeoDataFrame(geometry=primal_gdf.geometry.centroid, crs=primal_gdf.crs)
joined_gdf = gpd.sjoin(primal_centroids_gdf, bounds, how="left", predicate="intersects")
joined_gdf = joined_gdf[~joined_gdf.index.duplicated(keep="first")]
nodes_gdf["district"] = joined_gdf["NOMDIS"]
nodes_gdf["neighb"] = joined_gdf["NOMBRE"]

# %%
# population data - sampled at the dual node (street segment midpoint)
with open(PATH_POPULATION, "rb") as f:
    memfile = MemoryFile(f.read())
    with memfile.open() as dataset:
        pop_raster = dataset.read()
        for node_idx, node_row in tqdm(nodes_gdf.iterrows(), total=len(nodes_gdf)):
            pop_val = point_query(
                node_row.geometry,
                pop_raster,
                interpolate="nearest",
                nodata=-200,
                affine=dataset.transform,
            )[0]
            if pop_val is None:
                pop_val = 0
            nodes_gdf.at[node_idx, "pop_dens"] = np.clip(pop_val, 0, np.inf)
# convert from 100m2 to 1km2
nodes_gdf["pop_dens"] = nodes_gdf["pop_dens"] * 100

# %%
# length weighted centralities: segment_weighted=True weights each destination by the
# street length it represents (see README.md for per-column formulas)
cn.centrality_shortest(
    distances=CENT_DISTANCES,
    closeness=prefix_labels(SHORTEST_CLOSENESS),
    betweenness=prefix_labels(SHORTEST_BETWEENNESS),
    cycles=False,
    postprocess={"lw_hillier": "lw_density**2 / lw_farness"},
    segment_weighted=True,
)
cn.centrality_simplest(
    distances=CENT_DISTANCES,
    closeness=prefix_labels(SIMPLEST_CLOSENESS),
    betweenness=prefix_labels(SIMPLEST_BETWEENNESS),
    postprocess={"lw_hillier": "lw_density**2 / lw_farness"},
    segment_weighted=True,
)

# %%
# unweighted centralities
cn.centrality_shortest(
    distances=CENT_DISTANCES,
    closeness=SHORTEST_CLOSENESS,
    betweenness=SHORTEST_BETWEENNESS,
    cycles=True,
    postprocess={"hillier": "density**2 / farness"},
    segment_weighted=False,
)
cn.centrality_simplest(
    distances=CENT_DISTANCES,
    closeness=SIMPLEST_CLOSENESS,
    betweenness=SIMPLEST_BETWEENNESS,
    postprocess={"hillier": "density**2 / farness"},
    segment_weighted=False,
)

# %%
# load premises
premises = gpd.read_file(PATH_PREMISES)

# %%
# rename columns to english
premises_eng = premises.rename(
    columns={
        "id_local": "local_id",
        "id_distrito_local": "local_distr_id",
        "desc_distrito_local": "local_distr_desc",
        "id_barrio_local": "local_neighb_id",
        "desc_barrio_local": "local_neighb_desc",
        "cod_barrio_local": "local_neighb_code",
        "id_seccion_censal_local": "local_census_section_id",
        "desc_seccion_censal_local": "local_census_section_desc",
        "id_seccion": "section_id",
        "desc_seccion": "section_desc",
        "id_division": "division_id",
        "desc_division": "division_desc",
        "id_epigrafe": "epigraph_id",
        "desc_epigrafe": "epigraph_desc",
        "geometry": "geometry",
    }
)
# cast index to string
premises_eng.index = premises_eng.index.astype(str)
# map section descriptions to english
premises_eng["section_desc"] = premises_eng["section_desc"].replace(
    premises_lu_schema.section_schema
)
# map division descriptions to english
premises_eng["division_desc"] = premises_eng["division_desc"].replace(
    premises_lu_schema.division_schema
)
# remove none / null
premises_eng = premises_eng[~premises_eng["section_desc"].str.contains("none|null", na=False)]
premises_eng = premises_eng[
    ~premises_eng["division_desc"].str.contains("Null Value at Origin|No Activity", na=False)
]
# %%
# save cleaned version
premises_eng.to_file(PATH_OUT_PREMISES)

# %%
# compute mixed uses
# decay_fn=None emits both the unweighted (_nw) and beta weighted (_wt) hill columns
cn.compute_mixed_uses(
    premises_eng,
    landuse_column_label="division_desc",
    distances=LU_DISTANCES,
    decay_fn=None,
)
# compute mixed uses using simplest paths
cn.compute_mixed_uses(
    premises_eng,
    landuse_column_label="division_desc",
    distances=LU_DISTANCES,
    decay_fn=None,
    angular=True,
)
# compute accessibility
ACCESS_KEYS = [
    "food_bev",
    "creat_entert",
    "retail",
    "services",
    "education",
    "accommod",
    "sports_rec",
    "health",
]
cn.compute_accessibilities(
    premises_eng,
    landuse_column_label="division_desc",
    accessibility_keys=ACCESS_KEYS,
    distances=LU_DISTANCES,
    decay_fn=None,
)
# compute accessibility using simplest paths
cn.compute_accessibilities(
    premises_eng,
    landuse_column_label="division_desc",
    accessibility_keys=ACCESS_KEYS,
    distances=LU_DISTANCES,
    decay_fn=None,
    angular=True,
)

# %%
# assemble the output: computed columns joined to the primal street geometries
out_gdf = cn.to_geopandas()
# dual node location (street segment midpoint) as WKT, as in earlier builds
out_gdf["dual_node"] = nodes_gdf.geometry.to_wkt()
out_gdf["bearing"] = nodes_gdf["bearing"]
out_gdf["district"] = nodes_gdf["district"]
out_gdf["neighb"] = nodes_gdf["neighb"]
out_gdf["pop_dens"] = nodes_gdf["pop_dens"]
# drop unweighted hill columns to match the established dataset schema (weighted retained)
drop_cols = [col for col in out_gdf.columns if col.startswith("cc_hill_") and col.endswith("_nw")]
out_gdf = out_gdf.drop(columns=drop_cols)
# drop the nominal node weight column (always 1); seg_length carries the street lengths
out_gdf = out_gdf.drop(columns=["weight"])
# drop empty networkx attribute columns and the build status column
out_gdf = out_gdf.drop(
    columns=["names", "routes", "highways", "levels", "feature_status"], errors="ignore"
)

# %%
# save only live nodes located within a district
out_gdf_live = out_gdf[out_gdf.live]
out_gdf_live = out_gdf_live[~out_gdf_live.district.isna()]
# simplify geom if necessary
out_gdf_live.geometry = out_gdf_live.geometry.simplify(2)
# pare back data types to reduce size
for col in out_gdf_live.select_dtypes(include=["int64"]).columns:
    out_gdf_live[col] = out_gdf_live[col].astype("int32")
for col in out_gdf_live.select_dtypes(include=["float64"]).columns:
    out_gdf_live[col] = out_gdf_live[col].astype("float32")
# save; index=True writes the dual node key as the "index" column
out_gdf_live.to_file(PATH_OUT_DATASET, index=True)

# %%
# save subset
nodes_gdf_subset = out_gdf_live[
    out_gdf_live["district"].isin(
        [
            "Centro",
            "Arganzuela",
            "Retiro",
            "Salamanca",
            "Chamartín",
            "Tetuán",
            "Chamberí",
        ]
    )
]
nodes_gdf_subset.to_file(PATH_OUT_DATASET_SUBSET, index=True)
