# ============================================================
# Urban Spatial Knowledge Graph Relation Generator
# 完全重构稳定版（GeoPandas 0.14+）
#
# 功能：
# 1. 拓扑关系
# 2. 空间语义关系
# 3. 属性关系
# 4. 方位关系
#
# 输入：
# - 原始 geojson
# - 清洗后的 node json
#
# 输出：
# - knowledge_graph.json
# - spatial_semantic_relations.json
# - semantic_knowledge_graph.json
# - directional_relations.json
#
# 作者：ChatGPT 重构版
# ============================================================

import os
import json
import math
import numpy as np
import geopandas as gpd

from shapely.geometry import Point
from sklearn.cluster import DBSCAN

# ============================================================
# 配置
# ============================================================

PROJECT_CRS = 32649
OUTPUT_DIR = "../relationship"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# JSON 工具
# ============================================================

def load_json(path):

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(data, path):

    with open(path, "w", encoding="utf-8") as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

# ============================================================
# 构建 lookup
# ============================================================

def build_lookup(node_json):

    nodes = load_json(node_json)

    lookup = {}

    for n in nodes:

        entity = {
            "id": n["entity_id"],
            "name": n["name"],
            "type": n["label"],
            "properties": n.get("properties", {})
        }

        original_ids = n["properties"].get(
            "original_ids",
            []
        )

        for oid in original_ids:

            oid = str(oid)

            lookup[oid] = entity

            if "/" in oid:

                lookup[
                    oid.split("/")[-1]
                ] = entity

    return lookup

# ============================================================
# 统一读取 GeoJSON
# ============================================================

def load_gdf(path):

    gdf = gpd.read_file(path)

    if gdf.crs is None:

        gdf = gdf.set_crs(epsg=4326)

    gdf = gdf.to_crs(epsg=PROJECT_CRS)

    if "@id" in gdf.columns:

        gdf["id"] = gdf["@id"].astype(str)

    elif "id" in gdf.columns:

        gdf["id"] = gdf["id"].astype(str)

    else:

        gdf["id"] = gdf.index.astype(str)

    gdf = gdf.reset_index(drop=True)

    return gdf

# ============================================================
# 创建关系
# ============================================================

def create_relation(
        source,
        target,
        relation,
        relation_list,
        distance=None
):

    if source is None or target is None:
        return

    if source["id"] == target["id"]:
        return

    item = {

        "source_id": source["id"],
        "source_name": source["name"],
        "source_type": source["type"],

        "target_id": target["id"],
        "target_name": target["name"],
        "target_type": target["type"],

        "relation": relation
    }

    if distance is not None:

        item["distance"] = round(
            float(distance),
            2
        )

    relation_list.append(item)

# ============================================================
# 主函数
# ============================================================

def extract_relations(

        roads_geo,
        subways_geo,
        stations_geo,
        pois_geo,
        water_geo,

        roads_node,
        subways_node,
        stations_node,
        pois_node,
        water_node
):

    print("========== Loading Lookups ==========")

    road_lookup = build_lookup(roads_node)
    subway_lookup = build_lookup(subways_node)
    station_lookup = build_lookup(stations_node)
    poi_lookup = build_lookup(pois_node)
    water_lookup = build_lookup(water_node)

    print("Road Lookup:", len(road_lookup))
    print("POI Lookup:", len(poi_lookup))

    # ========================================================
    # 读取 GeoData
    # ========================================================

    print("========== Loading GeoData ==========")

    r_gdf = load_gdf(roads_geo)
    s_gdf = load_gdf(subways_geo)
    st_gdf = load_gdf(stations_geo)
    p_gdf = load_gdf(pois_geo)
    w_gdf = load_gdf(water_geo)

    print("Road CRS:", r_gdf.crs)

    # ========================================================
    # 中心点
    # ========================================================

    for gdf in [
        r_gdf,
        s_gdf,
        st_gdf,
        p_gdf,
        w_gdf
    ]:

        centroids = gdf.geometry.centroid

        gdf["cx"] = centroids.x
        gdf["cy"] = centroids.y

    # ========================================================
    # 1. 拓扑关系
    # ========================================================

    print("========== Topology Relations ==========")

    topology_relations = []

    # --------------------------------------------------------
    # CONNECTED
    # --------------------------------------------------------

    road_right = r_gdf.copy()

    join = gpd.sjoin(
        r_gdf,
        road_right,
        predicate="intersects"
    )

    for left_idx, row in join.iterrows():

        right_idx = row["index_right"]

        if left_idx == right_idx:
            continue

        geom1 = r_gdf.loc[left_idx].geometry
        geom2 = road_right.loc[right_idx].geometry

        if not (
            geom1.crosses(geom2)
            or geom1.touches(geom2)
        ):
            continue

        id1 = str(r_gdf.loc[left_idx]["id"])
        id2 = str(road_right.loc[right_idx]["id"])

        if id1 not in road_lookup:
            continue

        if id2 not in road_lookup:
            continue

        create_relation(
            road_lookup[id1],
            road_lookup[id2],
            "CONNECTED",
            topology_relations
        )

    # --------------------------------------------------------
    # INTERSECTS
    # --------------------------------------------------------

    road_right = r_gdf.copy()

    join = gpd.sjoin(
        s_gdf,
        road_right,
        predicate="intersects"
    )

    for left_idx, row in join.iterrows():

        right_idx = row["index_right"]

        sid = str(s_gdf.loc[left_idx]["id"])
        rid = str(road_right.loc[right_idx]["id"])

        if sid in subway_lookup \
        and rid in road_lookup:

            create_relation(
                subway_lookup[sid],
                road_lookup[rid],
                "INTERSECTS",
                topology_relations
            )

    # --------------------------------------------------------
    # LOCATED_ON
    # --------------------------------------------------------

    road_buffer = r_gdf.copy()

    road_buffer["geometry"] = \
        road_buffer.geometry.buffer(20)

    join = gpd.sjoin(
        p_gdf,
        road_buffer,
        predicate="within"
    )

    for left_idx, row in join.iterrows():

        right_idx = row["index_right"]

        pid = str(p_gdf.loc[left_idx]["id"])
        rid = str(r_gdf.loc[right_idx]["id"])

        if pid not in poi_lookup:
            continue

        if rid not in road_lookup:
            continue

        dist = p_gdf.loc[left_idx].geometry.distance(
            r_gdf.loc[right_idx].geometry
        )

        create_relation(
            poi_lookup[pid],
            road_lookup[rid],
            "LOCATED_ON",
            topology_relations,
            dist
        )

    # --------------------------------------------------------
    # CROSSES_WATER
    # --------------------------------------------------------

    join = gpd.sjoin(
        r_gdf,
        w_gdf,
        predicate="intersects"
    )

    for left_idx, row in join.iterrows():

        right_idx = row["index_right"]

        geom1 = r_gdf.loc[left_idx].geometry
        geom2 = w_gdf.loc[right_idx].geometry

        if not geom1.crosses(geom2):
            continue

        rid = str(r_gdf.loc[left_idx]["id"])
        wid = str(w_gdf.loc[right_idx]["id"])

        if rid in road_lookup \
        and wid in water_lookup:

            create_relation(
                road_lookup[rid],
                water_lookup[wid],
                "CROSSES_WATER",
                topology_relations
            )

    save_json(
        topology_relations,
        os.path.join(
            OUTPUT_DIR,
            "knowledge_graph.json"
        )
    )

    print("✅ topology_relations:", len(topology_relations))

    # ========================================================
    # 2. 空间语义关系
    # ========================================================

    print("========== Spatial Relations ==========")

    spatial_relations = []

    # --------------------------------------------------------
    # NEAR
    # --------------------------------------------------------

    join = gpd.sjoin(
        p_gdf,
        p_gdf,
        predicate="dwithin",
        distance=300
    )

    for left_idx, row in join.iterrows():

        right_idx = row["index_right"]

        if left_idx == right_idx:
            continue

        pid1 = str(p_gdf.loc[left_idx]["id"])
        pid2 = str(p_gdf.loc[right_idx]["id"])

        if pid1 not in poi_lookup:
            continue

        if pid2 not in poi_lookup:
            continue

        dist = p_gdf.loc[left_idx].geometry.distance(
            p_gdf.loc[right_idx].geometry
        )

        create_relation(
            poi_lookup[pid1],
            poi_lookup[pid2],
            "NEAR",
            spatial_relations,
            dist
        )

    # --------------------------------------------------------
    # AROUND
    # --------------------------------------------------------

    station_buffer = st_gdf.copy()

    station_buffer["geometry"] = \
        station_buffer.geometry.buffer(200)

    join = gpd.sjoin(
        p_gdf,
        station_buffer,
        predicate="within"
    )

    for left_idx, row in join.iterrows():

        right_idx = row["index_right"]

        pid = str(p_gdf.loc[left_idx]["id"])
        sid = str(st_gdf.loc[right_idx]["id"])

        if pid in poi_lookup \
        and sid in station_lookup:

            create_relation(
                poi_lookup[pid],
                station_lookup[sid],
                "AROUND",
                spatial_relations
            )

    # --------------------------------------------------------
    # WATERFRONT_OF
    # --------------------------------------------------------

    print("   -> WATERFRONT_OF")

    water_buffer = w_gdf.copy()

    water_buffer["geometry"] = \
        water_buffer.geometry.buffer(50)

    join = gpd.sjoin(
        r_gdf,
        water_buffer,
        predicate="intersects"
    )

    for left_idx, row in join.iterrows():

        right_idx = row["index_right"]

        road_geom = r_gdf.loc[left_idx].geometry

        water_geom = water_buffer.loc[
            right_idx
        ].geometry

        inter = road_geom.intersection(
            water_geom
        )

        if inter.length < 300:
            continue

        rid = str(r_gdf.loc[left_idx]["id"])
        wid = str(w_gdf.loc[right_idx]["id"])

        if rid in road_lookup \
        and wid in water_lookup:

            create_relation(
                road_lookup[rid],
                water_lookup[wid],
                "WATERFRONT_OF",
                spatial_relations
            )

    # --------------------------------------------------------
    # POI_CLUSTER
    # --------------------------------------------------------

    coords = np.array([

        [x, y]

        for x, y in zip(
            p_gdf["cx"],
            p_gdf["cy"]
        )
    ])

    if len(coords) > 0:

        db = DBSCAN(
            eps=500,
            min_samples=5
        ).fit(coords)

        p_gdf["cluster"] = db.labels_

        for _, row in p_gdf.iterrows():

            cid = row["cluster"]

            if cid == -1:
                continue

            pid = str(row["id"])

            if pid not in poi_lookup:
                continue

            cluster_entity = {

                "id": f"cluster_{cid}",
                "name": f"POI_CLUSTER_{cid}",
                "type": "Cluster"
            }

            create_relation(
                poi_lookup[pid],
                cluster_entity,
                "POI_CLUSTER",
                spatial_relations
            )

    save_json(
        spatial_relations,
        os.path.join(
            OUTPUT_DIR,
            "spatial_semantic_relations.json"
        )
    )

    print("✅ spatial_relations:", len(spatial_relations))

    # ========================================================
    # 3. 属性关系（轻量级版本）
    # 保留原始 JSON 属性，不再实体化 Coordinate / Property
    # ========================================================

    print("========== Semantic Relations ==========")

    semantic_relations = []

    node_paths = [

        roads_node,
        subways_node,
        stations_node,
        pois_node,
        water_node
    ]

    for path in node_paths:

        nodes = load_json(path)

        for n in nodes:

            entity_id = n["entity_id"]

            props = n.get("properties", {})

            # ----------------------------------------------------
            # 仅建立一个轻量 HAS_PROPERTY 关系
            # 不再拆分为 Property 实体
            # ----------------------------------------------------

            semantic_relations.append({

                "source_id": entity_id,
                "source_name": n["name"],
                "source_type": n["label"],

                "target_id": f"{entity_id}_properties",
                "target_name": f"{n['name']}_properties",
                "target_type": "Property",

                "relation": "HAS_PROPERTY",

                # 直接保留原始属性
                "properties": props
            })

    save_json(
        semantic_relations,
        os.path.join(
            OUTPUT_DIR,
            "semantic_knowledge_graph.json"
        )
    )

    print("✅ semantic_relations:", len(semantic_relations))

    # ========================================================
    # 4. 方位关系（精准聚焦于 POI 实体化方位，阻断边爆炸）
    # ========================================================

    print("========== Directional Relations (Pure POI Focus) ==========")

    directional_relations = []

    all_entities = []

    # 【核心重构】：彻底舍弃 roads, subways, stations, 只将 p_gdf (POI) 的重心直角坐标装入大网
    for _, row in p_gdf.iterrows():

        rid = str(row["id"])

        if rid in poi_lookup:

            ent = poi_lookup[rid]

            all_entities.append({
                "entity": ent,
                "x": row["cx"],
                "y": row["cy"]
            })

    OPPOSITE = {
        "NORTH_OF": "SOUTH_OF",
        "SOUTH_OF": "NORTH_OF",
        "EAST_OF": "WEST_OF",
        "WEST_OF": "EAST_OF",
        "NORTHEAST_OF": "SOUTHWEST_OF",
        "SOUTHWEST_OF": "NORTHEAST_OF",
        "NORTHWEST_OF": "SOUTHEAST_OF",
        "SOUTHEAST_OF": "NORTHWEST_OF"
    }

    # 5km 空间邻近过滤（利用空间直角系 R-Tree 快速碰撞邻居）
    if all_entities:

        points_gdf = gpd.GeoDataFrame(
            geometry=[Point(x["x"], x["y"]) for x in all_entities],
            data={"idx": list(range(len(all_entities)))},
            crs=f"EPSG:{PROJECT_CRS}"
        )

        points_right = points_gdf.copy().rename(columns={"idx": "idx_right"})

        directional_join = gpd.sjoin(
            points_gdf,
            points_right,
            predicate="dwithin",
            distance=5000  # 依然保持 5 公里城内局部邻近规则
        )

        for _, row in directional_join.iterrows():

            idx1 = int(row["idx"])
            idx2 = int(row["idx_right"])

            if idx1 >= idx2:
                continue

            e1 = all_entities[idx1]
            e2 = all_entities[idx2]

            dx = e2["x"] - e1["x"]
            dy = e2["y"] - e1["y"]

            angle = math.degrees(math.atan2(dy, dx))

            if angle < 0:
                angle += 360

            if 22.5 <= angle < 67.5: direction = "NORTHEAST_OF"
            elif 67.5 <= angle < 112.5: direction = "NORTH_OF"
            elif 112.5 <= angle < 157.5: direction = "NORTHWEST_OF"
            elif 157.5 <= angle < 202.5: direction = "WEST_OF"
            elif 202.5 <= angle < 247.5: direction = "SOUTHWEST_OF"
            elif 247.5 <= angle < 292.5: direction = "SOUTH_OF"
            elif 292.5 <= angle < 337.5: direction = "SOUTHEAST_OF"
            else: direction = "EAST_OF"

            create_relation(
                e2["entity"],
                e1["entity"],
                direction,
                directional_relations
            )

            create_relation(
                e1["entity"],
                e2["entity"],
                OPPOSITE[direction],
                directional_relations
            )

    save_json(
        directional_relations,
        os.path.join(
            OUTPUT_DIR,
            "directional_relations.json"
        )
    )

    print("✅ directional_relations:", len(directional_relations))
    # ========================================================

    total = \
        len(topology_relations) + \
        len(spatial_relations) + \
        len(semantic_relations) + \
        len(directional_relations)

    print("\n========== ALL COMPLETED ==========")
    print("TOTAL:", total)

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    extract_relations(

        roads_geo="../roads.geojson",
        subways_geo="../subways.geojson",
        stations_geo="../stations.geojson",
        pois_geo="../pois.geojson",
        water_geo="../water.geojson",

        roads_node="../data/road_nodes_final.json",
        subways_node="../data/subway_nodes_final.json",
        stations_node="../data/station_nodes_final.json",
        pois_node="../data/poi_nodes_final.json",
        water_node="../data/water_nodes_final.json"
    )