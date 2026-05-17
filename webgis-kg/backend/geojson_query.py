import geopandas as gpd

roads = gpd.read_file(
    "../data/wuhan_roads.geojson"
)

stations = gpd.read_file(
    "../data/wuhan_stations.geojson"
)

pois = gpd.read_file(
    "../data/wuhan_poi.geojson"
)

districts = gpd.read_file(
    "../data/wuhan.geojson"
)

# =========================
# nearby
# =========================

def nearby_pois(
    point,
    distance=500
):

    buffer_geom = point.buffer(
        distance
    )

    result = pois[
        pois.intersects(
            buffer_geom
        )
    ]

    return result.to_json()

# =========================
# inside
# =========================

def inside_district(
    point
):

    result = districts[
        districts.contains(
            point
        )
    ]

    return result.to_json()